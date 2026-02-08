"""
FastAPI Backend for Engineering Intelligence Platform
=====================================================
Exposes the multi-agent supervisor as REST + SSE streaming endpoints,
plus dedicated feature endpoints for frontend integration.

Designed for deployment on HuggingFace Spaces (port 7860) or any
container-based platform (Railway, Render, Fly.io).

Chat Endpoints:
    POST /api/chat          — Streaming SSE chat (supervisor routing)
    POST /api/chat/sync     — Synchronous JSON chat

Thread Management:
    POST /api/threads       — Create conversation thread
    GET  /api/threads       — List all threads
    DELETE /api/threads/{id} — Delete a thread

Feature Endpoints (direct pipeline access):
    POST /api/prep/1on1     — Generate 1:1 meeting briefing
    POST /api/anomalies     — Run anomaly detection on metrics
    POST /api/experts/find  — Find experts (quick or full Graph RAG)
    POST /api/search        — Semantic search (developers/projects)
    POST /api/metrics/dora  — Get DORA deployment metrics

System:
    GET  /api/health        — Health check (DB connectivity)
"""

from __future__ import annotations

import os
import sys
import time
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# ── Ensure the project root is on sys.path ─────────────────
# When running from /server, the parent dir (Datathon) has the agents package.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.supervisor import SupervisorAgent
from agents.utils.streaming import StreamEvent
from agents.utils.logger import get_logger

logger = get_logger(__name__, "API")


# ============================================================================
# Lifespan — initialise the supervisor once on startup
# ============================================================================

_supervisor: Optional[SupervisorAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise the supervisor agent (loads models, compiles graph)."""
    global _supervisor
    logger.info("🚀 Initialising supervisor agent…")
    _supervisor = SupervisorAgent()
    _supervisor.initialize()
    logger.info("✓ Supervisor ready — accepting requests")
    yield
    logger.info("Shutting down…")


def get_supervisor() -> SupervisorAgent:
    """Return the initialised supervisor; raise if not ready."""
    if _supervisor is None or not _supervisor._initialized:
        raise HTTPException(status_code=503, detail="Agent not initialised yet")
    return _supervisor


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Engineering Intelligence API",
    version="1.0.0",
    description="AI-native engineering analytics — multi-agent, multi-model, streaming.",
    lifespan=lifespan,
)

# ── CORS — allow all origins for hackathon / dev convenience ────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request / Response Models
# ============================================================================

class ChatRequest(BaseModel):
    """Body for /api/chat and /api/chat/sync."""
    message: str = Field(..., min_length=1, description="User query")
    thread_id: Optional[str] = Field(
        None, description="Conversation thread ID (omit for ephemeral)"
    )
    stream: bool = Field(True, description="Enable SSE streaming (default True)")


class ChatSyncResponse(BaseModel):
    """Response for /api/chat/sync."""
    response: str
    thread_id: Optional[str] = None
    model_used: Optional[str] = None
    task_type: Optional[str] = None
    elapsed_s: float = 0.0


class ThreadCreate(BaseModel):
    """Body for POST /api/threads."""
    title: str = Field("", description="Optional human-friendly title")


class ThreadInfo(BaseModel):
    """Single thread metadata."""
    thread_id: str
    title: str = ""
    created_at: Optional[str] = None
    message_count: int = 0


class HealthStatus(BaseModel):
    """Health check result."""
    status: str
    uptime_s: float
    agent_ready: bool
    databases: dict


# ── Feature Endpoint Models ────────────────────────────────

class PrepRequest(BaseModel):
    """Request for 1:1 meeting prep."""
    developer_name: str = Field(..., min_length=1, description="Developer name or email")
    manager_context: str = Field("", description="Optional manager notes or focus areas")


class PrepResponse(BaseModel):
    """Response for 1:1 meeting prep."""
    status: str
    developer_name: str
    team: Optional[str] = None
    role: Optional[str] = None
    briefing: str
    talking_points: list[str] = []
    elapsed_s: float = 0.0


class AnomalyRequest(BaseModel):
    """Request for anomaly detection."""
    project_id: Optional[str] = Field(None, description="Project to scope analysis (omit for all)")
    days_current: int = Field(7, ge=1, le=90, description="Current period in days")
    days_baseline: int = Field(30, ge=7, le=365, description="Baseline period in days")


class AnomalyResponse(BaseModel):
    """Response for anomaly detection."""
    status: str
    anomaly_count: int
    anomalies: list[dict] = []
    alert_text: str = ""
    quality_score: float = 0.0
    elapsed_s: float = 0.0


class ExpertRequest(BaseModel):
    """Request for expert discovery."""
    query: str = Field(..., min_length=1, description="Topic, skills, or question to find expert for")
    mode: str = Field("full", description="'quick' (vector-only) or 'full' (Graph RAG)")
    limit: int = Field(5, ge=1, le=20, description="Max experts to return")


class ExpertResponse(BaseModel):
    """Response for expert discovery."""
    status: str
    mode: str
    query: str
    experts: list[dict] = []
    report: str = ""
    elapsed_s: float = 0.0


class SearchRequest(BaseModel):
    """Request for semantic search."""
    query: str = Field(..., min_length=1, description="Natural language search query")
    search_type: Optional[str] = Field(None, description="Filter: 'developer_profile', 'project_doc', or omit for all")
    limit: int = Field(5, ge=1, le=50, description="Max results")


class SearchResponse(BaseModel):
    """Response for semantic search."""
    status: str
    query: str
    result_count: int
    results: list[dict] = []
    elapsed_s: float = 0.0


class DoraRequest(BaseModel):
    """Request for DORA metrics."""
    project_id: Optional[str] = Field(None, description="Project to filter (omit for all)")
    days: int = Field(30, ge=1, le=365, description="Analysis window in days")


class DoraResponse(BaseModel):
    """Response for DORA metrics."""
    status: str
    days: int
    summary: dict = {}
    projects: list[dict] = []
    elapsed_s: float = 0.0


# ============================================================================
# Helpers
# ============================================================================

_start_time = time.time()


def _sse_line(event: StreamEvent) -> str:
    """Format a StreamEvent as an SSE text frame."""
    payload = event.to_dict()
    return f"event: {payload['event']}\ndata: {json.dumps(payload)}\n\n"


async def _stream_generator(supervisor: SupervisorAgent, message: str, thread_id: Optional[str]):
    """
    Async generator that wraps the synchronous ``stream_query()`` generator.
    Runs the blocking LangGraph iteration in a thread pool so the event loop
    stays responsive.
    """
    loop = asyncio.get_event_loop()

    # We iterate the sync generator from a thread.  Each event is placed
    # onto an asyncio.Queue so the SSE response can yield it.
    q: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()

    def _run_sync():
        try:
            for event in supervisor.stream_query(message, thread_id=thread_id):
                asyncio.run_coroutine_threadsafe(q.put(event), loop)
        except Exception as exc:
            err = StreamEvent.error(message=str(exc))
            asyncio.run_coroutine_threadsafe(q.put(err), loop)
        finally:
            asyncio.run_coroutine_threadsafe(q.put(None), loop)  # sentinel

    loop.run_in_executor(None, _run_sync)

    while True:
        event = await q.get()
        if event is None:
            break
        yield _sse_line(event)


# ============================================================================
# Endpoints
# ============================================================================

# ── Chat (streaming SSE) ───────────────────────────────────

@app.post("/api/chat")
async def chat_stream(req: ChatRequest):
    """
    Main chat endpoint.  Streams Server-Sent Events (SSE) in real-time.

    Events emitted (in order):
        stream_start → model_selection → routing → agent_start →
        tool_start / tool_end (repeated) → response → agent_end → stream_end
    """
    if not req.stream:
        return await chat_sync(req)

    supervisor = get_supervisor()

    return StreamingResponse(
        _stream_generator(supervisor, req.message, req.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )


# ── Chat (synchronous JSON) ────────────────────────────────

@app.post("/api/chat/sync", response_model=ChatSyncResponse)
async def chat_sync(req: ChatRequest):
    """
    Synchronous chat — waits for the full response and returns JSON.
    Useful for simple integrations that don't support SSE.
    """
    supervisor = get_supervisor()
    loop = asyncio.get_event_loop()

    t0 = time.time()
    response_text = await loop.run_in_executor(
        None, supervisor.query, req.message, req.thread_id
    )
    elapsed = time.time() - t0

    return ChatSyncResponse(
        response=response_text,
        thread_id=req.thread_id,
        elapsed_s=round(elapsed, 2),
    )


# ── Thread Management ──────────────────────────────────────

@app.post("/api/threads", response_model=ThreadInfo)
async def create_thread(body: ThreadCreate):
    """Create a new conversation thread."""
    supervisor = get_supervisor()
    tid = supervisor.new_thread(title=body.title)
    return ThreadInfo(thread_id=tid, title=body.title)


@app.get("/api/threads", response_model=list[ThreadInfo])
async def list_threads():
    """List all conversation threads."""
    supervisor = get_supervisor()
    raw = supervisor.list_threads()
    return [
        ThreadInfo(
            thread_id=t.get("thread_id", ""),
            title=t.get("title", ""),
            created_at=t.get("created_at"),
            message_count=t.get("message_count", 0),
        )
        for t in raw
    ]


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a conversation thread."""
    supervisor = get_supervisor()
    ok = supervisor.delete_thread(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": True, "thread_id": thread_id}


# ============================================================================
# Feature Endpoints — Direct access to specialist pipelines
# ============================================================================

# ── 1:1 Meeting Prep ───────────────────────────────────────

@app.post("/api/prep/1on1", response_model=PrepResponse)
async def prep_one_on_one(req: PrepRequest):
    """
    Generate a 1:1 meeting briefing for a specific developer.
    
    Gathers recent activity, workload, collaboration patterns,
    and synthesizes an actionable briefing with talking points.
    """
    from agents.pipelines.prep_pipeline import prepare_one_on_one

    loop = asyncio.get_event_loop()
    t0 = time.time()

    try:
        result = await loop.run_in_executor(
            None, 
            lambda: prepare_one_on_one(
                developer_name=req.developer_name,
                manager_context=req.manager_context,
            )
        )
    except Exception as e:
        logger.error(f"Prep pipeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - t0
    status = result.get("status", "error")

    if status == "developer_not_found":
        raise HTTPException(status_code=404, detail=f"Developer '{req.developer_name}' not found")

    dev_info = result.get("developer_info", {})
    return PrepResponse(
        status=status,
        developer_name=dev_info.get("full_name", req.developer_name),
        team=dev_info.get("team_name"),
        role=dev_info.get("title") or dev_info.get("role"),
        briefing=result.get("briefing", ""),
        talking_points=result.get("talking_points", []),
        elapsed_s=round(elapsed, 2),
    )


# ── Anomaly Detection ──────────────────────────────────────

@app.post("/api/anomalies", response_model=AnomalyResponse)
async def detect_anomalies(req: AnomalyRequest):
    """
    Run anomaly detection on engineering metrics.
    
    Compares current metrics against historical baselines using AI reasoning,
    investigates root causes, and generates actionable alerts.
    """
    from agents.pipelines.anomaly_pipeline import run_anomaly_detection

    loop = asyncio.get_event_loop()
    t0 = time.time()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_anomaly_detection(
                project_id=req.project_id,
                days_current=req.days_current,
                days_baseline=req.days_baseline,
            )
        )
    except Exception as e:
        logger.error(f"Anomaly pipeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - t0
    anomalies = result.get("anomalies", [])

    return AnomalyResponse(
        status=result.get("status", "ok"),
        anomaly_count=len(anomalies),
        anomalies=anomalies,
        alert_text=result.get("alert_text", ""),
        quality_score=result.get("quality_score", 0.0),
        elapsed_s=round(elapsed, 2),
    )


# ── Expert Discovery ───────────────────────────────────────

@app.post("/api/experts/find", response_model=ExpertResponse)
async def find_experts(req: ExpertRequest):
    """
    Find the best expert for a topic or skill set.
    
    Modes:
        - 'quick': Vector-only fast search (no LLM synthesis)
        - 'full': Graph RAG with vector + knowledge graph fusion + LLM explanation
    """
    loop = asyncio.get_event_loop()
    t0 = time.time()

    try:
        if req.mode == "quick":
            # Vector-only fast search
            from agents.tools.vector_tools import find_developer_by_skills

            results = await loop.run_in_executor(
                None,
                lambda: find_developer_by_skills.invoke({"skills": req.query, "limit": req.limit})
            )

            experts = []
            if results and not (len(results) == 1 and "error" in results[0]):
                for dev in results:
                    experts.append({
                        "name": dev.get("full_name", "Unknown"),
                        "title": dev.get("title", ""),
                        "team": dev.get("team_name", ""),
                        "similarity": dev.get("similarity", 0),
                    })

            elapsed = time.time() - t0
            return ExpertResponse(
                status="ok",
                mode="quick",
                query=req.query,
                experts=experts,
                report=f"Found {len(experts)} developers matching '{req.query}'",
                elapsed_s=round(elapsed, 2),
            )

        else:
            # Full Graph RAG pipeline
            from agents.pipelines.graph_rag_pipeline import find_expert

            result = await loop.run_in_executor(
                None,
                lambda: find_expert(req.query, limit=req.limit)
            )

            ranking = result.get("fused_ranking", [])
            experts = []
            for r in ranking[:req.limit]:
                experts.append({
                    "name": r.get("name", "Unknown"),
                    "combined_score": r.get("combined_score", 0),
                    "vector_score": r.get("vector_score", 0),
                    "graph_score": r.get("graph_score", 0),
                    "expertise": r.get("expertise", []),
                })

            elapsed = time.time() - t0
            return ExpertResponse(
                status=result.get("status", "ok"),
                mode="full",
                query=req.query,
                experts=experts,
                report=result.get("report", ""),
                elapsed_s=round(elapsed, 2),
            )

    except Exception as e:
        logger.error(f"Expert search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Semantic Search ────────────────────────────────────────

@app.post("/api/search", response_model=SearchResponse)
async def semantic_search_endpoint(req: SearchRequest):
    """
    Search for semantically similar content using pgvector.
    
    Can search across all embeddings or filter by type:
        - 'developer_profile': Developer skills and bios
        - 'project_doc': Project descriptions and documentation
    """
    from agents.tools.vector_tools import semantic_search

    loop = asyncio.get_event_loop()
    t0 = time.time()

    try:
        results = await loop.run_in_executor(
            None,
            lambda: semantic_search.invoke({
                "query": req.query,
                "embedding_type": req.search_type,
                "limit": req.limit,
            })
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - t0

    # Handle error in results
    if results and len(results) == 1 and "error" in results[0]:
        raise HTTPException(status_code=500, detail=results[0]["error"])

    return SearchResponse(
        status="ok",
        query=req.query,
        result_count=len(results),
        results=results,
        elapsed_s=round(elapsed, 2),
    )


# ── DORA Metrics ───────────────────────────────────────────

@app.post("/api/metrics/dora", response_model=DoraResponse)
async def get_dora_metrics(req: DoraRequest):
    """
    Get DORA deployment metrics from ClickHouse.
    
    Returns:
        - Deployment frequency (per week)
        - Average lead time (hours)
        - Change failure rate (%)
        - MTTR (hours)
        - Per-project breakdown
    """
    from agents.tools.clickhouse_tools import get_deployment_metrics

    loop = asyncio.get_event_loop()
    t0 = time.time()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: get_deployment_metrics.invoke({
                "project_id": req.project_id,
                "days_back": req.days,
            })
        )
    except Exception as e:
        logger.error(f"DORA metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - t0

    # Handle error in result
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return DoraResponse(
        status="ok",
        days=req.days,
        summary=result.get("summary", {}),
        projects=result.get("projects", []),
        elapsed_s=round(elapsed, 2),
    )


# ── Health Check ────────────────────────────────────────────

@app.get("/api/health", response_model=HealthStatus)
async def health_check():
    """
    Reports system health including DB connectivity.
    """
    db_status = {}

    # PostgreSQL
    try:
        from agents.utils.db_clients import get_postgres_client
        pg = get_postgres_client()
        pg.execute_query("SELECT 1 AS test")
        db_status["postgres"] = "ok"
    except Exception as e:
        db_status["postgres"] = f"error: {e}"

    # ClickHouse
    try:
        from agents.utils.db_clients import get_clickhouse_client
        ch = get_clickhouse_client()
        ch.execute_query("SELECT 1 AS test")
        db_status["clickhouse"] = "ok"
    except Exception as e:
        db_status["clickhouse"] = f"error: {e}"

    # Neo4j
    try:
        from agents.utils.db_clients import get_neo4j_client
        neo = get_neo4j_client()
        neo.execute_query("RETURN 1 AS test")
        db_status["neo4j"] = "ok"
    except Exception as e:
        db_status["neo4j"] = f"error: {e}"

    agent_ok = _supervisor is not None and _supervisor._initialized
    overall = "healthy" if agent_ok and all(v == "ok" for v in db_status.values()) else "degraded"

    return HealthStatus(
        status=overall,
        uptime_s=round(time.time() - _start_time, 1),
        agent_ready=agent_ok,
        databases=db_status,
    )


# ── Root redirect ──────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "Engineering Intelligence API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


# ============================================================================
# Entrypoint (for local dev / HuggingFace Spaces)
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 7860))  # HF Spaces default
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
