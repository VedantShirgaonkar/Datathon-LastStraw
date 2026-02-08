"""
Combined Webhook + Agent Server

Single FastAPI application with:
- Webhook endpoints (GitHub, Jira, Notion) 
- Agent processing endpoint
- In-process agent execution (no HTTP forwarding)

Perfect for production deployment - one server, one port!
"""

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import logging
import os
from datetime import datetime
from uuid import uuid4
from typing import Optional
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agent.agent import DatabaseAgent
from agent.schemas.webhook_schemas import WebhookEvent, EventSource, AgentResponse
from agent.utils.normalize_github import normalize_github_event
from agent.utils.github_validator import validate_github_event, get_github_event_type
from agent.config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Engineering Intelligence Platform",
    description="Unified webhook receiver + AI agent for Jira/GitHub/Notion sync",
    version="1.0.0"
)

# Initialize agent and config
logger.info("🚀 Initializing LangGraph agent...")
try:
    agent = DatabaseAgent()
    logger.info("✅ Agent initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize agent: {e}")
    agent = None

config = get_config()


# ==============================================================================
# SIGNATURE VALIDATION
# ==============================================================================

def verify_github_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify GitHub webhook signature (HMAC SHA-256)"""
    if not signature_header:
        return False
    
    try:
        hash_algorithm, github_signature = signature_header.split('=')
    except ValueError:
        return False
    
    if hash_algorithm != 'sha256':
        return False
    
    mac = hmac.new(secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()
    
    return hmac.compare_digest(expected_signature, github_signature)


# ==============================================================================
# HEALTH & INFO ENDPOINTS
# ==============================================================================

@app.get("/")
async def root():
    """Main health check"""
    return {
        "status": "online",
        "service": "engineering-intelligence",
        "version": "1.0.0",
        "agent_ready": agent is not None,
        "endpoints": {
            "webhooks": ["/webhooks/github", "/webhooks/jira", "/webhooks/notion"],
            "agent": ["/agent/process", "/agent/health"]
        }
    }


@app.get("/health")
@app.get("/agent/health")
async def health_check():
    """Detailed health check"""
    health_data = {
        "status": "healthy" if agent else "degraded",
        "agent_initialized": agent is not None,
        "databases": {
            "postgres": "configured" if config.postgres_host else "not_configured",
            "clickhouse": "configured" if config.clickhouse_host else "not_configured",
            "neo4j": "configured" if config.neo4j_uri else "not_configured"
        },
        "integrations": {
            "jira": "configured" if config.jira_url else "not_configured",
            "github": "configured" if config.github_token else "not_configured",
            "featherless_ai": "configured" if config.featherless_api_key else "not_configured"
        }
    }
    return health_data


# ==============================================================================
# WEBHOOK ENDPOINTS
# ==============================================================================

@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """
    GitHub webhook endpoint with signature validation.
    Processes in-process via agent.
    """
    # Read raw body
    body = await request.body()
    
    # Verify signature
    if config.github_webhook_secret:
        if not verify_github_signature(body, x_hub_signature_256, config.github_webhook_secret):
            logger.warning("Invalid GitHub signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload robustly (handle bytes/encoding inconsistencies and form-encoded payload=...)
    from urllib.parse import unquote_plus
    payload = None
    raw_text = body.decode('utf-8', errors='replace') if body else ''

    # Check if body is URL-encoded form with payload=<json>
    if raw_text.startswith('payload='):
        try:
            # Extract everything after 'payload='
            payload_encoded = raw_text[len('payload='):]
            # Strip other form fields if present (separated by &)
            amp = payload_encoded.find('&')
            if amp != -1:
                payload_encoded = payload_encoded[:amp]
            # URL-decode and parse JSON
            payload_str = unquote_plus(payload_encoded)
            payload = json.loads(payload_str)
        except Exception as e:
            preview = (raw_text[:400] + "...") if raw_text else "<empty>"
            logger.warning(f"Failed to parse form-encoded payload (preview): {preview} | error: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON in form payload")

    # Otherwise attempt direct JSON parsing
    if payload is None:
        try:
            payload = json.loads(raw_text)
        except Exception:
            # Log a short, safe preview for debugging (do not log full secrets)
            preview = (raw_text[:400] + "...") if raw_text else "<empty>"
            logger.warning(f"Invalid JSON received from GitHub webhook (preview): {preview}")
            raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Create webhook event
    # Validate/infer event type, then normalize. Accept any payload if validation
    # or normalization fails and fall back to raw.
    try:
        is_valid, val_msg = validate_github_event(payload)
        if not is_valid:
            logger.warning(f"GitHub payload validation warning: {val_msg}")

        headers_dict = {k: v for k, v in request.headers.items()} if hasattr(request, 'headers') else {}
        inferred_event = get_github_event_type(payload, headers=headers_dict)
        event_name = x_github_event or inferred_event

        try:
            webhook_event = normalize_github_event(payload, event_name=event_name)
        except Exception as e:
            logger.warning(f"GitHub normalization failed, falling back to raw payload: {e}")
            webhook_event = WebhookEvent(
                event_id=f"gh_{uuid4().hex[:12]}",
                source=EventSource.GITHUB,
                event_type=event_name or (payload.get('action') if isinstance(payload, dict) else 'unknown'),
                timestamp=datetime.utcnow(),
                raw=payload
            )
    except Exception as e:
        logger.error(f"Unexpected error while validating/normalizing GitHub payload: {e}", exc_info=True)
        webhook_event = WebhookEvent(
            event_id=f"gh_{uuid4().hex[:12]}",
            source=EventSource.GITHUB,
            event_type=x_github_event or 'unknown',
            timestamp=datetime.utcnow(),
            raw=payload
        )
    
    logger.info(f"📥 GitHub: {webhook_event.event_type}")
    
    # Process with agent (in-process, no HTTP call!)
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        response: AgentResponse = agent.process_event(webhook_event)
        
        return JSONResponse(content={
            "status": "success" if response.success else "partial_success",
            "summary": response.summary,
            "actions_taken": response.actions_taken,
            "tools_executed": response.tools_executed,
            "errors": response.errors
        })
    except Exception as e:
        logger.error(f"❌ Agent error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/webhooks/jira")
async def jira_webhook(request: Request):
    """
    Jira webhook endpoint.
    Processes in-process via agent.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = payload.get("webhookEvent", "unknown")
    
    webhook_event = WebhookEvent(
        event_id=f"jira_{uuid4().hex[:12]}",
        source=EventSource.JIRA,
        event_type=event_type,
        timestamp=datetime.utcnow(),
        raw=payload
    )
    
    logger.info(f"📥 Jira: {webhook_event.event_type}")
    
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        response: AgentResponse = agent.process_event(webhook_event)
        
        return JSONResponse(content={
            "status": "success" if response.success else "partial_success",
            "summary": response.summary,
            "actions_taken": response.actions_taken,
            "tools_executed": response.tools_executed,
            "errors": response.errors
        })
    except Exception as e:
        logger.error(f"❌ Agent error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/webhooks/notion")
async def notion_webhook(request: Request):
    """
    Notion webhook endpoint.
    Processes in-process via agent.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = payload.get("type", "page_updated")
    
    webhook_event = WebhookEvent(
        event_id=f"notion_{uuid4().hex[:12]}",
        source=EventSource.NOTION,
        event_type=event_type,
        timestamp=datetime.utcnow(),
        raw=payload
    )
    
    logger.info(f"📥 Notion: {webhook_event.event_type}")
    
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        response: AgentResponse = agent.process_event(webhook_event)
        
        return JSONResponse(content={
            "status": "success" if response.success else "partial_success",
            "summary": response.summary,
            "actions_taken": response.actions_taken,
            "tools_executed": response.tools_executed,
            "errors": response.errors
        })
    except Exception as e:
        logger.error(f"❌ Agent error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# ==============================================================================
# AGENT ENDPOINT (for direct testing)
# ==============================================================================

@app.post("/agent/process")
async def process_event(request: Request, debug: bool = False):
    """
    Direct agent processing endpoint.
    
    Use this for testing or internal event processing.
    Accepts WebhookEvent JSON and runs full agent workflow.
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        event_data = await request.json()
        webhook_event = WebhookEvent(**event_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook event: {str(e)}")
    
    logger.info(f"📥 Direct: {webhook_event.source.value} / {webhook_event.event_type}")
    
    try:
        start_time = datetime.now()
        response: AgentResponse = agent.process_event(webhook_event)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        result = {
            "status": "success" if response.success else "partial_success",
            "summary": response.summary,
            "actions_taken": response.actions_taken,
            "tools_executed": response.tools_executed,
            "errors": response.errors,
            "processing_time_seconds": elapsed
        }
        
        if debug:
            result["debug"] = {
                "event_id": webhook_event.event_id,
                "source": webhook_event.source.value,
                "event_type": webhook_event.event_type
            }
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"❌ Agent error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# ==============================================================================
# ERROR HANDLERS
# ==============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"}
    )


# ==============================================================================
# RUN SERVER
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", config.webhook_server_port))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Starting Combined Server on {host}:{port}")
    logger.info(f"📡 Webhooks: /webhooks/{{github,jira,notion}}")
    logger.info(f"🤖 Agent: POST /agent/process")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
