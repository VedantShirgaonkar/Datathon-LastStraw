"""
Custom exceptions and exception handlers for the API.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse


class APIException(Exception):
    """Base exception for API errors."""
    
    def __init__(self, message: str, error_code: str, status_code: int = 500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)


class InvalidTokenError(APIException):
    """Raised when API token is invalid or expired."""
    
    def __init__(self, message: str = "Invalid or expired API token"):
        super().__init__(
            message=message,
            error_code="invalid_token",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class RateLimitError(APIException):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        super().__init__(
            message=message,
            error_code="rate_limit",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS
        )


class MissingEnvVarError(APIException):
    """Raised when required environment variable is missing."""
    
    def __init__(self, var_name: str):
        super().__init__(
            message=f"Missing required environment variable: {var_name}",
            error_code="configuration_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class InvalidRepoError(APIException):
    """Raised when repository name is invalid or not found."""
    
    def __init__(self, repo_name: str):
        super().__init__(
            message=f"Repository '{repo_name}' not found or not configured",
            error_code="not_found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class TimeoutError(APIException):
    """Raised when request times out."""
    
    def __init__(self, message: str = "Request timed out"):
        super().__init__(
            message=message,
            error_code="timeout",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT
        )


class ExternalAPIError(APIException):
    """Raised when external API returns an error."""
    
    def __init__(self, service: str, message: str, status_code: int = 502):
        super().__init__(
            message=f"{service} API error: {message}",
            error_code="external_api_error",
            status_code=status_code
        )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Global exception handler for API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unexpected errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred"
        }
    )
