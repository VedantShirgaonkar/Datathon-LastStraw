"""
Configuration management using Pydantic Settings.
Loads environment variables from .env file.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Webhook Secrets (optional, for signature verification)
    github_webhook_secret: Optional[str] = Field(default=None, description="GitHub webhook secret for HMAC verification")
    jira_webhook_secret: Optional[str] = Field(default=None, description="Jira webhook secret for HMAC verification")
    
    # Notion Configuration (still uses REST API)
    notion_token: str = Field(..., description="Notion integration token")
    notion_database_id: str = Field(..., description="Notion database ID")
    
    # HTTP Client Configuration
    request_timeout: int = Field(default=10, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars not defined in the model


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid reading .env file on every request.
    """
    return Settings()
