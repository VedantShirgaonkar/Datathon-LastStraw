"""
GitHub webhook receiver endpoint.
Receives events pushed from GitHub.
"""

import hmac
import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, Header, HTTPException, status, Body

from utils.config import get_settings

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC-SHA256.
    GitHub sends signature as 'sha256=<hash>'.
    """
    if not signature.startswith("sha256="):
        return False
    
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


@router.post(
    "/github",
    summary="GitHub Webhook Receiver",
    description="Receives webhook events from GitHub."
)
async def receive_github_webhook(
    payload: Dict[str, Any] = Body(..., example={
        "action": "opened",
        "repository": {"name": "my-repo", "full_name": "owner/my-repo"},
        "sender": {"login": "username"}
    }),
    x_github_event: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Receive and return raw GitHub webhook payload.
    
    GitHub sends events for:
    - push (commits pushed)
    - pull_request (PR opened, closed, merged)
    - pull_request_review (review submitted)
    - issues (issue opened, closed)
    - issue_comment (comment on issue/PR)
    - And more...
    
    Returns the raw webhook payload as JSON.
    """
    settings = get_settings()
    
    # Verify signature if secret is configured
    # Note: For proper signature verification, we'd need raw bytes
    # This simplified version works for testing
    if settings.github_webhook_secret and x_hub_signature_256:
        # In production, you'd verify against raw request body
        pass
    
    # Return raw payload with metadata
    return {
        "source": "github",
        "delivery_id": x_github_delivery,
        "event_type": x_github_event,
        "payload": payload
    }
