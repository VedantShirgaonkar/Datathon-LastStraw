from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from pr_merge_agent.clickhouse_client import ClickHouseClient
from pr_merge_agent.config import get_settings
from pr_merge_agent.github_client import GitHubClient
from pr_merge_agent.signing import verify_token


app = FastAPI(title="PR Merge Agent", version="1.0.0")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/actions/merge", response_class=HTMLResponse)
def merge_action(token: str):
    settings = get_settings()
    if not settings.pr_merge_agent_signing_secret:
        raise HTTPException(status_code=500, detail="Signing secret not configured")

    ok, payload, err = verify_token(token, settings.pr_merge_agent_signing_secret)
    if not ok or not payload:
        raise HTTPException(status_code=403, detail=f"Invalid token: {err}")

    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    actor = payload.get("actor") or "lead"
    if not repo or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repo/pr_number")

    gh = GitHubClient(settings.github_token)
    ch = ClickHouseClient(settings)

    pr_number_int = int(pr_number)
    pr = gh.get_pr(repo, pr_number_int)
    if pr.get("merged") is True:
        return HTMLResponse(f"<h3>Already merged: {repo} #{pr_number_int}</h3>")

    mergeable, mergeable_state = gh.get_mergeability(repo, pr_number_int)
    if mergeable is not True:
        return HTMLResponse(
            f"<h3>Not mergeable: {repo} #{pr_number_int}</h3>"
            f"<p>mergeable={mergeable} state={mergeable_state}</p>"
            f"<p><a href='{pr.get('html_url')}'>Open PR</a></p>"
        )

    result = gh.merge_pr(repo, pr_number_int, method=settings.github_merge_method)

    entity_id = f"pr:{repo}#{pr_number_int}"
    project_id = settings.project_id_for_repo(repo)
    ch.insert_event(
        source="github",
        event_type=settings.clickhouse_pr_merged_event_type,
        project_id=project_id,
        actor_id=str(actor),
        entity_id=entity_id,
        entity_type="pull_request",
        metadata={
            "repo": repo,
            "pr_number": pr_number_int,
            "merged_by": actor,
            "merge_method": settings.github_merge_method,
            "github_result": result,
            "pr_url": pr.get("html_url"),
            "merged_at": datetime.now(timezone.utc).isoformat(),
        },
        timestamp=datetime.now(timezone.utc),
    )

    return HTMLResponse(
        f"<h3>Merged: {repo} #{pr_number_int}</h3>"
        f"<p><a href='{pr.get('html_url')}'>Open PR</a></p>"
        f"<p>GitHub message: {result.get('message')}</p>"
    )
