"""
Jira webhook receiver endpoint.
Receives events pushed from Jira Cloud.
"""

import hmac
import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status, Body

from utils.config import get_settings

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/jira",
    summary="Jira Webhook Receiver",
    description="Receives webhook events from Jira Cloud."
)
async def receive_jira_webhook(
    payload: Dict[str, Any] = Body(..., example={
        "webhookEvent": "jira:issue_created",
        "issue": {"key": "PROJ-123", "fields": {"summary": "Test issue"}},
        "user": {"displayName": "John Doe"}
    }),
    x_atlassian_webhook_identifier: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Receive and return raw Jira webhook payload.
    
    Jira sends events for:
    - Issue created, updated, deleted
    - Comment added, updated, deleted
    - Sprint events
    - Board events
    - And more...
    
    Returns the raw webhook payload as JSON.
    """
    # Return raw payload with metadata
    return {
        "source": "jira",
        "webhook_id": x_atlassian_webhook_identifier,
        "event_type": payload.get("webhookEvent"),
        "payload": payload
    }
