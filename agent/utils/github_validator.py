"""
GitHub Webhook Payload Validator.

Validates incoming GitHub webhook events and extracts event type.
"""
from typing import Any


# Required fields that must be present in any GitHub webhook
REQUIRED_FIELDS = ["action"]  # Most GitHub webhooks have an action

# Common GitHub webhook event types and their identifying fields
EVENT_TYPE_INDICATORS = {
    "push": ["ref", "commits", "pusher"],
    "pull_request": ["pull_request", "action"],
    "issues": ["issue", "action"],
    "issue_comment": ["issue", "comment", "action"],
    "create": ["ref", "ref_type"],
    "delete": ["ref", "ref_type"],
    "release": ["release", "action"],
    "workflow_run": ["workflow_run", "action"],
    "check_run": ["check_run", "action"],
    "check_suite": ["check_suite", "action"],
    "deployment": ["deployment"],
    "deployment_status": ["deployment_status", "deployment"],
    "status": ["state", "sha", "commit"],
}


def validate_github_event(payload: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a GitHub webhook payload.
    
    Args:
        payload: The raw webhook payload
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a dictionary"
    
    if not payload:
        return False, "Payload is empty"
    
    # Basic structural checks: allow through but flag if repository missing
    if "repository" not in payload and "zen" not in payload:
        # Not a ping event and no repository - still allow but warn upstream
        return True, "missing repository"
    
    return True, None


def get_github_event_type(payload: dict[str, Any], headers: dict[str, str] | None = None) -> str:
    """
    Extract the event type from a GitHub webhook payload.
    
    GitHub sends the event type in the X-GitHub-Event header, but we can also
    try to infer it from the payload structure.
    
    Args:
        payload: The raw webhook payload
        headers: Optional request headers (contains X-GitHub-Event)
    
    Returns:
        The event type string
    """
    # Prefer header if available (most reliable)
    if headers:
        event_type = headers.get("X-GitHub-Event") or headers.get("x-github-event")
        if event_type:
            return event_type
    
    # Try to infer from payload structure
    for event_type, indicators in EVENT_TYPE_INDICATORS.items():
        if all(indicator in payload for indicator in indicators):
            return event_type
    
    # Check for ping event
    if "zen" in payload and "hook_id" in payload:
        return "ping"
    
    # Fallback to action if present, otherwise unknown
    action = payload.get("action", "unknown")
    return f"unknown_{action}"
