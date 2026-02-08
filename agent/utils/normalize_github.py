"""Utilities to normalize GitHub webhook payloads into the agent WebhookEvent format.

This normalizer produces the same shapes the agent previously received from
the Kafka pipeline (see Docs/AI_AGENT_INTEGRATION.md). The normalized event
places the compact, enriched representation directly under `raw` (no nested
`normalized` wrapper) and preserves the original payload when useful.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
import uuid

from agent.schemas.webhook_schemas import WebhookEvent, EventSource


def _parse_iso_timestamp(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.utcnow()


def _extract_user_email(user_obj: Dict[str, Any]) -> str | None:
    if not user_obj:
        return None
    # GitHub webhook may include an email in nested objects
    return user_obj.get('email') or user_obj.get('username') or None


def normalize_github_event(payload: Dict[str, Any], event_name: str | None = None) -> WebhookEvent:
    """Normalize GitHub payloads into the agent schema examples.

    Produces `raw` shaped like the examples in `Docs/AI_AGENT_INTEGRATION.md`.
    Supports: push, pull_request, issues, issue_comment. Falls back to a generic
    shape for unknown events.
    """
    if not event_name:
        if 'commits' in payload:
            event_name = 'push'
        elif 'pull_request' in payload:
            event_name = 'pull_request'
        elif 'issue' in payload and 'comment' in payload:
            event_name = 'issue_comment'
        elif 'issue' in payload:
            event_name = 'issues'
        else:
            event_name = payload.get('action') or 'unknown'

    repo = payload.get('repository') or {}

    enriched = {}

    if event_name == 'push':
        pusher = payload.get('pusher') or {}
        commits = payload.get('commits', []) or []

        # build commits list matching docs
        commits_out = []
        for c in commits:
            commits_out.append({
                'id': c.get('id'),
                'message': c.get('message'),
                'author': c.get('author', {}),
                'added': c.get('added', []),
                'modified': c.get('modified', []),
                'removed': c.get('removed', [])
            })

        # try to get an enriched email from head_commit or pusher
        head_commit = payload.get('head_commit') or (commits[-1] if commits else None)
        enriched_email = None
        if head_commit:
            enriched_email = _extract_user_email(head_commit.get('author', {}))
        if not enriched_email:
            enriched_email = _extract_user_email(pusher)

        raw = {
            'ref': payload.get('ref'),
            'pusher': {'name': pusher.get('name'), 'email': pusher.get('email')},
            'commits': commits_out,
            'head_commit': head_commit,
            'repository': {'name': repo.get('name'), 'full_name': repo.get('full_name')}
        }

        if enriched_email:
            raw['_enriched'] = {'user_email': enriched_email}

        ts = None
        if head_commit and head_commit.get('timestamp'):
            ts = _parse_iso_timestamp(head_commit.get('timestamp'))

    elif event_name == 'pull_request':
        pr = payload.get('pull_request', {})
        pr_user = pr.get('user') or {}
        pr_user_email = _extract_user_email(pr_user)

        raw = {
            'action': payload.get('action'),
            'number': payload.get('number') or pr.get('number'),
            'pull_request': {
                'title': pr.get('title'),
                'body': pr.get('body'),
                'state': pr.get('state'),
                'user': pr_user,
                'head': pr.get('head'),
                'base': pr.get('base'),
                'html_url': pr.get('html_url')
            },
            '_enriched': {'user_email': pr_user_email} if pr_user_email else {}
        }

        ts = None
        if pr and pr.get('updated_at'):
            ts = _parse_iso_timestamp(pr.get('updated_at'))

    elif event_name == 'issues':
        issue = payload.get('issue') or {}
        issue_user = issue.get('user') or {}
        issue_user_email = _extract_user_email(issue_user)

        raw = {
            'action': payload.get('action'),
            'issue': {
                'number': issue.get('number'),
                'title': issue.get('title') or issue.get('fields', {}).get('summary'),
                'body': issue.get('body') or issue.get('fields', {}).get('description'),
                'state': issue.get('state'),
                'user': issue_user,
                'labels': issue.get('labels', []),
                'html_url': issue.get('html_url')
            },
            '_enriched': {'user_email': issue_user_email} if issue_user_email else {}
        }

        ts = None
        if issue and issue.get('updated_at'):
            ts = _parse_iso_timestamp(issue.get('updated_at'))

    elif event_name == 'issue_comment':
        comment = payload.get('comment') or {}
        issue = payload.get('issue') or {}
        commenter = comment.get('user') or {}
        commenter_email = _extract_user_email(commenter)

        raw = {
            'action': payload.get('action'),
            'issue': {'number': issue.get('number'), 'title': issue.get('title')},
            'comment': {
                'body': comment.get('body'),
                'user': commenter,
                'html_url': comment.get('html_url')
            },
            '_enriched': {'user_email': commenter_email} if commenter_email else {}
        }

        ts = None
        if comment and comment.get('created_at'):
            ts = _parse_iso_timestamp(comment.get('created_at'))

    else:
        # Generic fallback keeps original payload under 'raw' key
        raw = payload
        ts = None

    if not ts:
        ts = datetime.utcnow()

    event_id = f"gh_{uuid.uuid4().hex[:12]}"

    return WebhookEvent(
        event_id=event_id,
        source=EventSource.GITHUB,
        event_type=event_name,
        timestamp=ts,
        raw=raw
    )
