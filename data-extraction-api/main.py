"""
FastAPI Data Extraction Backend

Exposes webhook receivers for:
- Jira Cloud (webhook)
- GitHub (webhook)
- Notion (REST API)

This backend receives raw webhook payloads and returns them as JSON.
No normalization, transformation, or database storage.
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from routers import health_router, notion_router, jira_webhook_router, github_webhook_router
from utils.config import get_settings
from utils.exceptions import APIException, api_exception_handler, generic_exception_handler


# Load environment variables from .env file
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Validates configuration on startup.
    """
    # Validate all required environment variables on startup
    try:
        settings = get_settings()
        print(f"✅ Configuration loaded successfully")
        print(f"   - Notion Database ID: {settings.notion_database_id[:8]}...")
        print(f"   - GitHub Webhook Secret: {'configured' if settings.github_webhook_secret else 'not set'}")
        print(f"   - Jira Webhook Secret: {'configured' if settings.jira_webhook_secret else 'not set'}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        raise
    
    yield  # Application runs here
    
    # Cleanup on shutdown
    print("🛑 Shutting down...")


# Initialize FastAPI application
app = FastAPI(
    title="Data Extraction API",
    description="""
## Raw Data Extraction Backend

Receives webhook events and queries data from enterprise sources.

### Supported Sources
- **Jira Cloud** - Webhook receiver for issue events
- **GitHub** - Webhook receiver for PR, commit, and issue events
- **Notion** - REST API for database queries and pages

### Webhook Endpoints
- `POST /webhooks/jira` - Receives Jira events
- `POST /webhooks/github` - Receives GitHub events (HMAC verified)

### Notes
- All responses are raw JSON payloads
- No normalization or transformation
- Configure webhook secrets via environment variables
    """,
    version="2.0.0",
    lifespan=lifespan
)

# Register exception handlers
app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include routers
app.include_router(health_router)
app.include_router(jira_webhook_router)
app.include_router(github_webhook_router)
app.include_router(notion_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
