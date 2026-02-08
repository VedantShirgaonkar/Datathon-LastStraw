"""
ClickHouse Tools for Agent System
==================================
Provides tools for querying time-series event data and DORA metrics
from ClickHouse Cloud.

Tables:
    events              – 131 rows of raw engineering events (commits, PR reviews, deploys, etc.)
    dora_daily_metrics  – 65 rows of daily DORA-style aggregates per project
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call, log_db_query
from agents.utils.db_clients import get_clickhouse_client

logger = get_logger(__name__, "CLICKHOUSE_TOOLS")


def _serialise_ch(rows: List[Dict]) -> List[Dict]:
    """Convert ClickHouse types (UUID, date, datetime) for JSON safety."""
    import math
    out = []
    for row in rows:
        clean: Dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, (datetime, date)):
                clean[k] = v.isoformat()
            elif hasattr(v, "hex"):
                clean[k] = str(v)
            elif isinstance(v, float) and (v != v or math.isinf(v)):  # NaN/Inf
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out


@tool
def query_events(
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source: Optional[str] = None,
    days_back: int = 30,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Query raw engineering events from the ClickHouse events table.

    Args:
        event_type: Filter by type (e.g. 'commit', 'pr_merged', 'pr_reviewed', 'deploy')
        actor_id:   Filter by actor email / ID
        project_id: Filter by project slug (e.g. 'proj-api')
        source:     Filter by source system (e.g. 'github', 'jira')
        days_back:  Look-back window in days (default 30)
        limit:      Max rows (default 100)

    Returns:
        List of event records with event_id, timestamp, source, event_type,
        project_id, actor_id, entity_id, entity_type, and metadata.
    """
    logger.debug(f"query_events: type={event_type}, actor={actor_id}, project={project_id}, days={days_back}")

    try:
        ch = get_clickhouse_client()

        query = f"SELECT * FROM events WHERE timestamp >= now() - INTERVAL {int(days_back)} DAY"

        if event_type:
            query += f" AND event_type = '{event_type}'"
        if actor_id:
            query += f" AND actor_id = '{actor_id}'"
        if project_id:
            query += f" AND project_id = '{project_id}'"
        if source:
            query += f" AND source = '{source}'"

        query += f" ORDER BY timestamp DESC LIMIT {int(limit)}"

        log_db_query(logger, "clickhouse", query, {})
        results = ch.execute_query(query)

        events = _serialise_ch(results)
        # Parse metadata JSON strings
        for evt in events:
            if isinstance(evt.get("metadata"), str):
                try:
                    evt["metadata"] = json.loads(evt["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

        log_tool_call(logger, "query_events", {"type": event_type, "days": days_back}, f"{len(events)} events")
        return events

    except Exception as e:
        log_tool_call(logger, "query_events", {"type": event_type}, error=e)
        return [{"error": str(e)}]


@tool
def get_deployment_metrics(
    project_id: Optional[str] = None,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Get DORA deployment metrics from the dora_daily_metrics table.

    Computes:
      - deployment_frequency (per week)
      - avg_lead_time_hours
      - change_failure_rate (failed / total deployments)
      - total deployments, PRs merged, commits, story points

    Args:
        project_id: Project slug to filter (e.g. 'proj-api'). All projects if omitted.
        days_back:  Analysis window in days (default 30)

    Returns:
        Dict with DORA metrics and a per-project breakdown.
    """
    logger.debug(f"get_deployment_metrics: project={project_id}, days={days_back}")

    try:
        ch = get_clickhouse_client()

        where = f"WHERE date >= today() - {int(days_back)}"
        if project_id:
            where += f" AND project_id = '{project_id}'"

        # Aggregate metrics
        agg_query = f"""
            SELECT
                project_id,
                sum(deployments)                AS total_deployments,
                sum(failed_deployments)         AS total_failed,
                avg(avg_lead_time_hours)        AS avg_lead_time_hours,
                sum(prs_merged)                 AS total_prs_merged,
                sum(commits)                    AS total_commits,
                sum(story_points_completed)     AS total_story_points,
                count()                         AS days_tracked
            FROM dora_daily_metrics
            {where}
            GROUP BY project_id
            ORDER BY total_deployments DESC
        """

        log_db_query(logger, "clickhouse", "DORA metrics aggregate", {"project": project_id, "days": days_back})
        rows = ch.execute_query(agg_query)
        rows = _serialise_ch(rows)

        # Build per-project breakdown
        projects: List[Dict] = []
        total_deps = 0
        total_failed = 0
        total_prs = 0
        total_commits = 0
        total_sp = 0
        lead_times: List[float] = []

        for r in rows:
            deps = int(r.get("total_deployments", 0))
            failed = int(r.get("total_failed", 0))
            days_tracked = int(r.get("days_tracked", 1))
            lt_raw = r.get("avg_lead_time_hours")

            # ClickHouse may return NaN as None (after _serialise_ch) or as str
            import math
            try:
                lt = float(lt_raw) if lt_raw is not None else None
                if lt is not None and (math.isnan(lt) or math.isinf(lt)):
                    lt = None
            except (ValueError, TypeError):
                lt = None

            cfr = (failed / deps * 100) if deps > 0 else 0.0
            freq_per_week = deps / max(days_tracked / 7, 1)

            proj_metrics = {
                "project_id": r["project_id"],
                "deployments": deps,
                "failed_deployments": failed,
                "change_failure_rate_pct": round(cfr, 1),
                "deployment_freq_per_week": round(freq_per_week, 1),
                "avg_lead_time_hours": round(lt, 1) if lt is not None else None,
                "prs_merged": int(r.get("total_prs_merged", 0)),
                "commits": int(r.get("total_commits", 0)),
                "story_points": int(r.get("total_story_points", 0)),
            }
            projects.append(proj_metrics)

            total_deps += deps
            total_failed += failed
            total_prs += int(r.get("total_prs_merged", 0))
            total_commits += int(r.get("total_commits", 0))
            total_sp += int(r.get("total_story_points", 0))
            if lt is not None:
                lead_times.append(lt)

        # Overall summary
        overall_cfr = (total_failed / total_deps * 100) if total_deps > 0 else 0.0
        valid_lead_times = [lt for lt in lead_times if lt is not None]
        overall_lt = sum(valid_lead_times) / len(valid_lead_times) if valid_lead_times else None

        result = {
            "period_days": days_back,
            "total_deployments": total_deps,
            "total_failed_deployments": total_failed,
            "change_failure_rate_pct": round(overall_cfr, 1),
            "avg_lead_time_hours": round(overall_lt, 1) if overall_lt else None,
            "total_prs_merged": total_prs,
            "total_commits": total_commits,
            "total_story_points": total_sp,
            "projects": projects,
        }

        log_tool_call(logger, "get_deployment_metrics", {"project": project_id, "days": days_back}, result)
        return result

    except Exception as e:
        log_tool_call(logger, "get_deployment_metrics", {"project": project_id}, error=e)
        return {"error": str(e)}


@tool
def get_developer_activity(
    actor_id: Optional[str] = None,
    project_id: Optional[str] = None,
    days_back: int = 7,
) -> List[Dict[str, Any]]:
    """
    Get developer activity summary from the events table.

    Aggregates commits, PRs, reviews, and deploys per actor for the given period.

    Args:
        actor_id:   Filter by actor email / ID (optional, all actors if omitted)
        project_id: Filter by project slug (optional)
        days_back:  Look-back window in days (default 7)

    Returns:
        List of activity summaries per developer with event breakdowns.
    """
    logger.debug(f"get_developer_activity: actor={actor_id}, project={project_id}, days={days_back}")

    try:
        ch = get_clickhouse_client()

        where = f"WHERE timestamp >= now() - INTERVAL {int(days_back)} DAY"
        if actor_id:
            where += f" AND actor_id = '{actor_id}'"
        if project_id:
            where += f" AND project_id = '{project_id}'"

        query = f"""
            SELECT
                actor_id,
                countIf(event_type = 'commit')      AS commits,
                countIf(event_type = 'pr_merged')    AS prs_merged,
                countIf(event_type = 'pr_reviewed')  AS prs_reviewed,
                countIf(event_type = 'deploy')       AS deploys,
                count()                              AS total_events,
                groupUniqArray(project_id)           AS active_projects,
                groupUniqArray(source)               AS sources
            FROM events
            {where}
            GROUP BY actor_id
            ORDER BY total_events DESC
        """

        log_db_query(logger, "clickhouse", "developer activity aggregate", {"actor": actor_id, "days": days_back})
        rows = ch.execute_query(query)
        activities = _serialise_ch(rows)

        log_tool_call(
            logger, "get_developer_activity",
            {"actor": actor_id, "days": days_back},
            f"{len(activities)} developers",
        )
        return activities

    except Exception as e:
        log_tool_call(logger, "get_developer_activity", {"actor": actor_id}, error=e)
        return [{"error": str(e)}]


# Export all tools for registration
CLICKHOUSE_TOOLS = [
    query_events,
    get_deployment_metrics,
    get_developer_activity,
]
