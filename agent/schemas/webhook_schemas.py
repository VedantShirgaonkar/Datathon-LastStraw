"""
Webhook Event Schemas

Replaces KafkaEvent with WebhookEvent for direct webhook processing.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ==============================================================================
# ENUMS
# ==============================================================================

class EventSource(str, Enum):
    """Event source types"""
    GITHUB = "github"
    JIRA = "jira"
    NOTION = "notion"
    PROMETHEUS = "prometheus"
    AI_AGENT = "ai_agent"


# ==============================================================================
# WEBHOOK EVENT SCHEMA
# ==============================================================================

class WebhookEvent(BaseModel):
    """Webhook event schema (replaces KafkaEvent)"""
    event_id: Optional[str] = Field(None, description="Unique event identifier (auto-generated if not provided)")
    source: EventSource
    event_type: str = Field(..., description="Specific event type (e.g., push, pull_request, issue_created)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw: Dict[str, Any] = Field(..., description="Original webhook payload from source system")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt_abc123",
                "source": "github",
                "event_type": "pull_request",
                "timestamp": "2026-02-08T08:00:00Z",
                "raw": {
                    "action": "opened",
                    "number": 42,
                    "pull_request": {
                        "title": "Add feature",
                        "user": {"login": "johndoe", "email": "john@company.com"}
                    }
                }
            }
        }


class EventClassification(BaseModel):
    """Event classification result"""
    source: EventSource
    event_type: str
    developer_email: Optional[EmailStr] = None
    project_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class ToolCall(BaseModel):
    """Tool call specification"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str


class ToolResult(BaseModel):
    """Tool execution result"""
    tool_name: str
    call_id: str
    success: bool
    result: Any
    error: Optional[str] = None


class AgentResponse(BaseModel):
    """Final agent response"""
    summary: str
    actions_taken: list[str]
    tools_executed: int
    errors: list[str]
    success: bool
