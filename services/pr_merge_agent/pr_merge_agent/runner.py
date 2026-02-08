from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from jinja2 import Environment, PackageLoader, select_autoescape

from pr_merge_agent.clickhouse_client import ClickHouseClient, PendingPr
from pr_merge_agent.config import get_settings
from pr_merge_agent.emailer import Emailer
from pr_merge_agent.github_client import GitHubClient
from pr_merge_agent.neo4j_client import Neo4jClient
from pr_merge_agent.signing import sign_payload
from pr_merge_agent.summarizer import summarize_pr


env = Environment(
    loader=PackageLoader("pr_merge_agent", "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def _merge_link(base_url: str, token: str) -> str:
    return base_url.rstrip("/") + "/actions/merge?token=" + token


def _pr_url(repo: str, pr_number: int) -> str:
    return f"https://github.com/{repo}/pull/{pr_number}"


def _entity_id(repo: str, pr_number: int) -> str:
    return f"pr:{repo}#{pr_number}"


def _email_subject_ready(repo: str, pr_number: int, title: str) -> str:
    return f"[PR Ready] {repo} #{pr_number} — {title}"


def _email_subject_conflict(repo: str, pr_number: int, title: str) -> str:
    return f"[PR Needs Attention] {repo} #{pr_number} — {title}"


def _extract_repo_and_number(settings, pr: Dict[str, Any]) -> Optional[PendingPr]:
    repo_full = ((pr.get("base") or {}).get("repo") or {}).get("full_name")
    number = pr.get("number")
    if not repo_full or not number:
        return None
    repo_full = str(repo_full)
    return PendingPr(repo=repo_full, pr_number=int(number), project_id=settings.project_id_for_repo(repo_full))


def get_pending_prs(settings, ch: ClickHouseClient, gh: GitHubClient) -> List[PendingPr]:
    # 1) Prefer ClickHouse-derived pending PRs, if your pipeline logs PR-open events.
    pending = ch.pending_prs_from_events(settings.pr_open_event_types_list(), settings.clickhouse_pr_merged_event_type)
    if pending:
        return pending

    # 2) Fallback: ask GitHub for open PRs in configured repos and treat those as pending,
    #    then skip ones already marked merged in ClickHouse.
    out: List[PendingPr] = []
    for repo in settings.repos_list():
        for pr in gh.list_open_prs(repo):
            pr_ref = _extract_repo_and_number(settings, pr)
            if not pr_ref:
                continue
            if ch.has_pr_merged_event(pr_ref.repo, pr_ref.pr_number, settings.clickhouse_pr_merged_event_type):
                continue
            out.append(pr_ref)
    return out


def run_once() -> int:
    settings = get_settings()

    dry_run = os.getenv("PR_MERGE_AGENT_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}

    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN is required")
    if not settings.neo4j_enabled() and not settings.lead_emails_list():
        raise RuntimeError("Either NEO4J or LEAD_EMAILS must be configured")
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is required")
    if not settings.pr_merge_agent_signing_secret:
        raise RuntimeError("PR_MERGE_AGENT_SIGNING_SECRET is required")

    ch = ClickHouseClient(settings)
    gh = GitHubClient(settings.github_token)
    emailer = Emailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        email_from=settings.email_from,
    )

    # Initialize Neo4j client if configured
    neo4j: Optional[Neo4jClient] = None
    if settings.neo4j_enabled():
        neo4j = Neo4jClient(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )

    def get_recipients_for_repo(repo: str) -> List[str]:
        """Get email recipients for a repo: Neo4j lookup with fallback to LEAD_EMAILS."""
        if neo4j:
            try:
                leads = neo4j.get_leads_for_repo(repo, settings.lead_roles_list())
                if leads:
                    return leads
            except Exception as e:
                print(f"⚠️ Neo4j lookup failed for {repo}: {e}")
        return settings.lead_emails_list()

    pending_prs = get_pending_prs(settings, ch, gh)
    sent = 0

    for pending in pending_prs:
        if not dry_run and ch.recently_emailed(pending.repo, pending.pr_number, settings.email_dedupe_minutes):
            continue

        pr = gh.get_pr(pending.repo, pending.pr_number)
        title = pr.get("title") or "(no title)"

        files = gh.get_pr_files(pending.repo, pending.pr_number)
        summary = summarize_pr(pr, files)

        mergeable, mergeable_state = gh.get_mergeability(pending.repo, pending.pr_number)

        # Get dynamic recipients based on repo ownership
        recipients = get_recipients_for_repo(pending.repo)
        if not recipients:
            print(f"⚠️ No recipients found for {pending.repo}, skipping")
            continue

        if mergeable is True:
            expires = int(time.time()) + 60 * 60 * 24
            token = sign_payload(
                {"repo": pending.repo, "pr_number": pending.pr_number, "actor": "lead"},
                settings.pr_merge_agent_signing_secret,
                expires,
            )
            merge_url = _merge_link(settings.pr_merge_agent_base_url, token)

            html = env.get_template("pr_ready.html").render(
                repo=pending.repo,
                pr_number=pending.pr_number,
                title=title,
                pr_url=pr.get("html_url") or _pr_url(pending.repo, pending.pr_number),
                merge_url=merge_url,
                summary=summary,
            )
            text = (
                f"PR ready to merge: {pending.repo} #{pending.pr_number}\n"
                f"{title}\n\n"
                f"Open PR: {pr.get('html_url') or _pr_url(pending.repo, pending.pr_number)}\n"
                f"Merge: {merge_url}\n\n"
                f"Summary:\n{summary}\n"
            )

            if dry_run:
                print("\n" + "=" * 72)
                print("DRY RUN (no email sent)")
                print(f"To: {', '.join(recipients)}")
                print(f"Subject: {_email_subject_ready(pending.repo, pending.pr_number, title)}")
                print(f"Open PR: {pr.get('html_url') or _pr_url(pending.repo, pending.pr_number)}")
                print(f"Merge URL: {merge_url}")
                print("\nSummary:\n" + summary)
                print("=" * 72 + "\n")
            else:
                emailer.send_html(
                    to_emails=recipients,
                    subject=_email_subject_ready(pending.repo, pending.pr_number, title),
                    html=html,
                    text=text,
                )

        else:
            html = env.get_template("pr_conflict.html").render(
                repo=pending.repo,
                pr_number=pending.pr_number,
                title=title,
                pr_url=pr.get("html_url") or _pr_url(pending.repo, pending.pr_number),
                mergeable_state=mergeable_state or "unknown",
                summary=summary,
            )
            text = (
                f"PR needs attention: {pending.repo} #{pending.pr_number}\n"
                f"{title}\n\n"
                f"Open PR: {pr.get('html_url') or _pr_url(pending.repo, pending.pr_number)}\n"
                f"mergeable={mergeable} state={mergeable_state}\n\n"
                f"Summary:\n{summary}\n"
            )
            if dry_run:
                print("\n" + "=" * 72)
                print("DRY RUN (no email sent)")
                print(f"To: {', '.join(recipients)}")
                print(f"Subject: {_email_subject_conflict(pending.repo, pending.pr_number, title)}")
                print(f"Open PR: {pr.get('html_url') or _pr_url(pending.repo, pending.pr_number)}")
                print(f"GitHub mergeable: {mergeable} state: {mergeable_state}")
                print("\nSummary:\n" + summary)
                print("=" * 72 + "\n")
            else:
                emailer.send_html(
                    to_emails=recipients,
                    subject=_email_subject_conflict(pending.repo, pending.pr_number, title),
                    html=html,
                    text=text,
                )

        if not dry_run:
            ch.insert_event(
                source="pr_merge_agent",
                event_type="pr_merge_email_sent",
                project_id=pending.project_id,
                actor_id="pr_merge_agent",
                entity_id=_entity_id(pending.repo, pending.pr_number),
                entity_type="pull_request",
                metadata={
                    "repo": pending.repo,
                    "pr_number": pending.pr_number,
                    "mergeable": mergeable,
                    "mergeable_state": mergeable_state,
                    "to": recipients,
                },
                timestamp=datetime.now(timezone.utc),
            )

        sent += 1

    # Cleanup Neo4j connection
    if neo4j:
        neo4j.close()

    return sent


if __name__ == "__main__":
    count = run_once()
    print(f"✅ Emails sent: {count}")
