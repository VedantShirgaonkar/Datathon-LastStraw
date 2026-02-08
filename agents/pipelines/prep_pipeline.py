"""
1:1 Meeting Prep Pipeline (Feature 2.3)
=========================================
LangGraph sub-graph that prepares personalized 1:1 meeting briefings
for managers by gathering developer activity, workload, collaboration
patterns, and synthesizing actionable talking points.

Pipeline:
    resolve_developer → gather_activity → gather_workload
        → gather_collaboration → synthesize_briefing → END
"""

from __future__ import annotations

import json
from typing import TypedDict, Optional, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from agents.utils.logger import get_logger, log_llm_call
from agents.utils.config import get_config
from agents.utils.model_router import get_llm
from agents.utils.db_clients import get_postgres_client, get_clickhouse_client

logger = get_logger(__name__, "PREP_PIPELINE")

_BRIEFING_MODEL = "gpt-4-turbo"


def _get_pipeline_llm(temperature: float = 0.3):
    """Get LLM for prep pipeline using centralized routing."""
    return get_llm(temperature=temperature)


# ============================================================================
# State
# ============================================================================

class PrepState(TypedDict):
    """State flowing through the 1:1 prep pipeline."""
    # Input
    developer_name: str           # Name or identifier of the developer
    manager_context: str          # Optional context from the manager

    # Resolved data
    developer_info: dict          # PostgreSQL employee record
    project_assignments: list     # Projects they're assigned to
    recent_activity: dict         # ClickHouse event activity
    workload_info: dict           # Workload and allocation details
    collaboration_patterns: list  # Collaboration data
    skill_context: list           # Semantic search results for skills/expertise

    # Output
    briefing: str                 # Final 1:1 prep briefing document
    talking_points: list          # Extracted talking points
    status: str                   # "ok" | "error" | "developer_not_found"
    error: Optional[str]          # Error message if status is error


# ============================================================================
# Node 1: Resolve developer identity
# ============================================================================

def resolve_developer_node(state: PrepState) -> dict:
    """Look up the developer in PostgreSQL."""
    name = state["developer_name"]
    logger.info(f"Resolving developer: {name}")

    try:
        pg = get_postgres_client()
        rows = pg.execute_query("""
            SELECT e.id, e.name as full_name, e.email, e.role, e.role as title, 
                   0.0 as hourly_rate, 'Unknown' as level, 'Unknown' as location, 
                   'UTC' as timezone, 'Full-time' as employment_type,
                   e.hire_date as start_date, true as active, t.name AS team_name
            FROM employees e
            LEFT JOIN teams t ON e.team_id = t.id
            WHERE e.name ILIKE %s OR e.email ILIKE %s
            LIMIT 1
        """, (f"%{name}%", f"%{name}%"))

        if not rows:
            logger.warning(f"Developer not found: {name}")
            return {"developer_info": {}, "status": "developer_not_found"}

        dev = _safe_dict(rows[0])

        # Schema Mismatch: employees.id is INT, project_assignments.employee_id is UUID.
        # We cannot join them. Disabling assignment fetching for now.
        assignments = []
        # assignments = pg.execute_query("""
        #     SELECT p.name AS project_name, p.status, p.priority,
        #            pa.role AS assignment_role, pa.allocated_percent,
        #            pa.start_date, pa.end_date
        #     FROM project_assignments pa
        #     JOIN projects p ON pa.project_id = p.id
        #     WHERE pa.employee_id = %s::uuid
        # """, (str(dev["id"]),))

        logger.info(f"Resolved: {dev.get('full_name')} ({dev.get('title')}), "
                     f"assignments skipped (schema mismatch)")

        return {
            "developer_info": dev,
            "project_assignments": [_safe_dict(a) for a in assignments],
            "status": "ok",
        }

    except Exception as e:
        logger.error(f"Failed to resolve developer: {e}")
        return {"developer_info": {}, "status": "error", "error": str(e)}


# ============================================================================
# Node 2: Gather recent activity from ClickHouse
# ============================================================================

def gather_activity_node(state: PrepState) -> dict:
    """Fetch recent developer activity from ClickHouse events."""
    if state.get("status") != "ok":
        return {"recent_activity": {}}

    dev = state.get("developer_info", {})
    email = dev.get("email", "")
    name = dev.get("full_name", "")
    logger.info(f"Gathering activity for {name} ({email})")

    try:
        ch = get_clickhouse_client()

        # Activity summary for last 14 days
        activity_q = f"""
            SELECT
                countIf(event_type = 'commit') AS commits,
                countIf(event_type = 'pr_merged') AS prs_merged,
                countIf(event_type = 'pr_reviewed') AS prs_reviewed,
                countIf(event_type = 'deploy') AS deploys,
                count() AS total_events,
                groupUniqArray(project_id) AS active_projects,
                min(timestamp) AS first_event,
                max(timestamp) AS last_event
            FROM events
            WHERE actor_id = '{email}'
              AND timestamp >= now() - INTERVAL 14 DAY
        """
        summary = ch.execute_query(activity_q)

        # Daily breakdown for last 7 days
        daily_q = f"""
            SELECT
                toDate(timestamp) AS date,
                count() AS events,
                countIf(event_type = 'commit') AS commits,
                countIf(event_type = 'pr_merged') AS prs_merged
            FROM events
            WHERE actor_id = '{email}'
              AND timestamp >= now() - INTERVAL 7 DAY
            GROUP BY date
            ORDER BY date DESC
        """
        daily = ch.execute_query(daily_q)

        # Recent events (last 10)
        recent_q = f"""
            SELECT event_type, project_id, timestamp, metadata
            FROM events
            WHERE actor_id = '{email}'
            ORDER BY timestamp DESC
            LIMIT 10
        """
        recent_events = ch.execute_query(recent_q)

        activity = {
            "summary_14d": _safe_serialise(summary),
            "daily_7d": _safe_serialise(daily),
            "recent_events": _safe_serialise(recent_events),
        }

        total = summary[0].get("total_events", 0) if summary else 0
        logger.info(f"Activity: {total} events in 14 days, "
                     f"{len(daily)} days with activity")
        return {"recent_activity": activity}

    except Exception as e:
        logger.error(f"Failed to gather activity: {e}")
        return {"recent_activity": {"error": str(e)}}


# ============================================================================
# Node 3: Gather workload information
# ============================================================================

def gather_workload_node(state: PrepState) -> dict:
    """Compute workload metrics from project assignments and DORA data."""
    if state.get("status") != "ok":
        return {"workload_info": {}}

    dev = state.get("developer_info", {})
    assignments = state.get("project_assignments", [])
    logger.info(f"Computing workload for {dev.get('full_name')}")

    try:
        # Compute allocation
        total_alloc = sum(a.get("allocated_percent", 0) or 0 for a in assignments)
        active_projects = [a for a in assignments
                          if a.get("status") in ("active", "in_progress", None)]

        # Get project-level DORA metrics for their projects
        ch = get_clickhouse_client()
        project_ids = [a.get("project_name", "") for a in assignments]

        project_metrics = []
        for proj in project_ids[:5]:  # limit to top 5
            if not proj:
                continue
            # Use project_id from events (slug format)
            rows = ch.execute_query(f"""
                SELECT
                    project_id,
                    sum(deployments) AS deployments,
                    sum(commits) AS commits,
                    sum(prs_merged) AS prs_merged,
                    sum(story_points_completed) AS story_points
                FROM dora_daily_metrics
                WHERE date >= today() - 14
                GROUP BY project_id
            """)
            project_metrics.extend(_safe_serialise(rows))

        workload = {
            "total_allocation_pct": total_alloc,
            "num_active_projects": len(active_projects),
            "overallocated": total_alloc > 100,
            "underallocated": total_alloc < 60,
            "hourly_rate": dev.get("hourly_rate"),
            "project_metrics": project_metrics,
        }

        logger.info(f"Workload: {total_alloc}% allocated, "
                     f"{len(active_projects)} active projects")
        return {"workload_info": workload}

    except Exception as e:
        logger.error(f"Failed to compute workload: {e}")
        return {"workload_info": {"error": str(e)}}


# ============================================================================
# Node 4: Gather collaboration patterns
# ============================================================================

def gather_collaboration_node(state: PrepState) -> dict:
    """Find collaboration patterns from event co-occurrence and embeddings."""
    if state.get("status") != "ok":
        return {"collaboration_patterns": [], "skill_context": []}

    dev = state.get("developer_info", {})
    email = dev.get("email", "")
    logger.info(f"Gathering collaboration patterns for {dev.get('full_name')}")

    try:
        ch = get_clickhouse_client()

        # Find co-contributors on same projects
        collab_q = f"""
            SELECT
                b.actor_id AS collaborator,
                count() AS shared_events,
                groupUniqArray(b.project_id) AS shared_projects
            FROM events a
            JOIN events b ON a.project_id = b.project_id
                AND a.actor_id != b.actor_id
                AND abs(dateDiff('day', a.timestamp, b.timestamp)) <= 3
            WHERE a.actor_id = '{email}'
              AND a.timestamp >= now() - INTERVAL 30 DAY
            GROUP BY b.actor_id
            ORDER BY shared_events DESC
            LIMIT 10
        """
        collabs = ch.execute_query(collab_q)
        collab_patterns = _safe_serialise(collabs)

        # Get skill context from embeddings
        pg = get_postgres_client()
        skill_rows = pg.execute_query("""
            SELECT title, content, source_table, metadata
            FROM embeddings
            WHERE source_table = 'employees' AND title ILIKE %s
            LIMIT 5
        """, (f"%{dev.get('full_name', '')}%",))
        skill_context = [_safe_dict(r) for r in skill_rows]

        logger.info(f"Collaboration: {len(collab_patterns)} collaborators, "
                     f"{len(skill_context)} skill embeddings")
        return {
            "collaboration_patterns": collab_patterns,
            "skill_context": skill_context,
        }

    except Exception as e:
        logger.error(f"Failed to gather collaboration data: {e}")
        return {"collaboration_patterns": [], "skill_context": []}


# ============================================================================
# Node 5: Synthesize briefing (LLM)
# ============================================================================

def synthesize_briefing_node(state: PrepState) -> dict:
    """Use LLM to synthesize all gathered data into a 1:1 prep briefing."""
    dev = state.get("developer_info", {})

    if state.get("status") == "developer_not_found":
        return {
            "briefing": f"❌ Developer '{state['developer_name']}' not found in the system.",
            "talking_points": [],
        }
    if state.get("status") == "error":
        err_msg = state.get("error", "Unknown error")
        return {
            "briefing": f"❌ Error preparing briefing for '{state['developer_name']}': {err_msg}",
            "talking_points": [],
        }

    logger.info(f"Synthesizing 1:1 briefing for {dev.get('full_name')}")

    llm = _get_pipeline_llm(temperature=0.4)

    prompt = f"""You are preparing a 1:1 meeting briefing for a manager meeting with their developer.

DEVELOPER PROFILE:
{json.dumps(dev, indent=2, default=str)[:1000]}

PROJECT ASSIGNMENTS:
{json.dumps(state.get('project_assignments', []), indent=2, default=str)[:1200]}

RECENT ACTIVITY (last 14 days):
{json.dumps(state.get('recent_activity', {}), indent=2, default=str)[:1500]}

WORKLOAD:
{json.dumps(state.get('workload_info', {}), indent=2, default=str)[:800]}

COLLABORATION PATTERNS:
{json.dumps(state.get('collaboration_patterns', []), indent=2, default=str)[:800]}

SKILLS & CONTEXT:
{json.dumps(state.get('skill_context', []), indent=2, default=str)[:800]}

{f"MANAGER'S NOTES: {state.get('manager_context', '')}" if state.get('manager_context') else ""}

Generate a structured 1:1 prep briefing with these sections:

1. **📋 Quick Profile** — Name, role, team, tenure summary
2. **🎯 Recent Accomplishments** — What they've shipped/achieved (be specific with data)
3. **⚠️ Concerns & Red Flags** — Activity drops, overallocation, blocked work (be tactful)
4. **💬 Suggested Talking Points** — 4-6 specific conversation starters, phrased as questions/discussion prompts
5. **🌱 Growth Opportunities** — Collaboration suggestions, skill development, stretch assignments
6. **📊 Key Metrics** — Activity numbers, workload percentage, deployment involvement

Be specific and actionable. Reference actual data. Frame concerns with empathy.
Keep it under 600 words.
"""

    try:
        log_llm_call(logger, _BRIEFING_MODEL, prompt_preview=prompt[:200])
        response = llm.invoke([
            SystemMessage(content="You create insightful, empathetic 1:1 meeting briefings for engineering managers."),
            HumanMessage(content=prompt),
        ])
        briefing = response.content.strip()

        # Extract talking points from the briefing
        talking_points = _extract_talking_points(briefing)

        logger.info(f"Briefing generated ({len(briefing)} chars, "
                     f"{len(talking_points)} talking points)")
        return {
            "briefing": briefing,
            "talking_points": talking_points,
        }

    except Exception as e:
        logger.error(f"Briefing synthesis failed: {e}")
        return {
            "briefing": f"Error generating briefing: {e}",
            "talking_points": [],
        }


# ============================================================================
# Graph Builder
# ============================================================================

_graph = None


def get_prep_graph():
    """Build and cache the 1:1 prep LangGraph."""
    global _graph
    if _graph is not None:
        return _graph

    logger.info("Building 1:1 prep sub-graph...")
    workflow = StateGraph(PrepState)

    workflow.add_node("resolve", resolve_developer_node)
    workflow.add_node("gather_activity", gather_activity_node)
    workflow.add_node("gather_workload", gather_workload_node)
    workflow.add_node("gather_collaboration", gather_collaboration_node)
    workflow.add_node("synthesize", synthesize_briefing_node)

    # Linear pipeline
    workflow.set_entry_point("resolve")
    workflow.add_edge("resolve", "gather_activity")
    workflow.add_edge("gather_activity", "gather_workload")
    workflow.add_edge("gather_workload", "gather_collaboration")
    workflow.add_edge("gather_collaboration", "synthesize")
    workflow.add_edge("synthesize", END)

    _graph = workflow.compile()
    logger.info("✓ 1:1 prep graph compiled")
    return _graph


# ============================================================================
# Public API
# ============================================================================

def prepare_one_on_one(
    developer_name: str,
    manager_context: str = "",
) -> dict:
    """
    Prepare a 1:1 meeting briefing for a developer.

    Args:
        developer_name: Name or email of the developer.
        manager_context: Optional notes/context from the manager.

    Returns:
        dict with keys: briefing, talking_points, developer_info, status
    """
    graph = get_prep_graph()

    initial_state: PrepState = {
        "developer_name": developer_name,
        "manager_context": manager_context,
        "developer_info": {},
        "project_assignments": [],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }

    logger.info(f"📋 Preparing 1:1 briefing for: {developer_name}")
    final_state = graph.invoke(initial_state)

    return {
        "briefing": final_state.get("briefing", ""),
        "talking_points": final_state.get("talking_points", []),
        "developer_info": final_state.get("developer_info", {}),
        "status": final_state.get("status", "ok"),
    }


# ============================================================================
# Helpers
# ============================================================================

def _safe_dict(row: Any) -> dict:
    """Convert a database row to a JSON-safe dict."""
    from datetime import datetime, date as date_type
    if not isinstance(row, dict):
        return {}
    clean = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date_type)):
            clean[k] = v.isoformat()
        elif hasattr(v, "hex"):
            clean[k] = str(v)
        else:
            clean[k] = v
    return clean


def _safe_serialise(rows: list) -> list:
    """Safely serialise database rows."""
    import math
    from datetime import datetime, date as date_type
    out = []
    for row in rows:
        clean = {}
        for k, v in (row.items() if isinstance(row, dict) else enumerate(row)):
            if isinstance(v, (datetime, date_type)):
                clean[k] = v.isoformat()
            elif isinstance(v, float) and (v != v or math.isinf(v)):
                clean[k] = None
            elif hasattr(v, "hex"):
                clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def _extract_talking_points(briefing: str) -> list:
    """Extract talking points from the briefing text."""
    import re
    points = []
    # Look for lines that start with bullet points or numbered items under talking points section
    in_section = False
    for line in briefing.split("\n"):
        if "talking point" in line.lower() or "conversation" in line.lower():
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped.startswith(("-", "•", "*")) or re.match(r"^\d+\.", stripped):
                # Clean up the point
                point = re.sub(r"^[-•*\d.]+\s*", "", stripped).strip()
                if point and len(point) > 10:
                    points.append(point)
            elif stripped.startswith("#") or stripped.startswith("**") and not stripped.startswith("**Q"):
                # New section header — stop extracting
                if points:  # only stop if we already found some
                    in_section = False
    return points[:8]  # cap at 8
