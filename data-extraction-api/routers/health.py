"""
Health check endpoint.
"""

from fastapi import APIRouter

from schemas.responses import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the health status of the API."
)
async def health_check() -> HealthResponse:
    """Check if the API is healthy and running."""
    return HealthResponse(status="ok")
