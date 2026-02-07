"""
Response schemas for the API.
"""

from typing import List
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response."""
    status: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str


class ReposResponse(BaseModel):
    """Response containing list of configured repositories."""
    repos: List[str]
