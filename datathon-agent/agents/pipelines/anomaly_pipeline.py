"""
Anomaly Detection Pipeline (Feature 2.1)
==========================================
LangGraph sub-graph that detects anomalies in engineering metrics,
investigates root causes by cross-referencing multiple data sources,
and generates actionable alerts with severity scores.

Pipeline:
    fetch_current → fetch_baseline → detect_anomalies
        → investigate_root_causes → generate_alert → evaluate_alert
        ├── (quality good) → done
        └── (quality poor) → refine → evaluate (loop, max 2 retries)

Uses ClickHouse for metrics, PostgreSQL for developer/project context.
"""

from __future__ import annotations

import json
from typing import TypedDict, Optional, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from agents.utils.logger import get_logger, log_llm_call
from agents.utils.config import get_config
from agents.utils.db_clients import get_clickhouse_client, get_postgres_client

logger = get_logger(__name__, "ANOMALY_PIPELINE")

MAX_REFINE_RETRIES = 2


# ============================================================================
# State
# ============================================================================

class AnomalyState(TypedDict):
    """State flowing through the anomaly detection graph."""
    # Inputs
    project_id: Optional[str]     # Scope to a specific project, or None for all
    days_current: int             # Window for "current" period (e.g. 7 days)
    days_baseline: int            # Window for "baseline" period (e.g. 30 days)

    # Pipeline artifacts
    current_metrics: dict         # Latest metrics from ClickHouse
    baseline_metrics: dict        # Historical baseline for comparison
    anomalies: list               # Detected anomalies with severity
    investigation: str            # Root-cause investigation results
    alert_text: str               # Generated alert text
    quality_score: float          # Self-evaluation score (0-1)
    quality_feedback: str         # Why the score was given
    refine_count: int             # How many times we refined
    status: str                   # "ok" | "anomalies_found" | "error"


# ============================================================================
# Node 1: Fetch current metrics
# ============================================================================

def fetch_current_node(state: AnomalyState) -> dict:
    """Fetch current-period metrics from ClickHouse."""
    logger.info(f"Fetching current metrics (last {state['days_current']} days)")

    try:
        ch = get_clickhouse_client()
        days = int(state["days_current"])
        proj = state.get("project_id")

        where = f"WHERE date >= today() - {days}"
        if proj:
            where += f" AND project_id = '{proj}'"

        # DORA-style aggregate
        dora_q = f"""
            SELECT
                project_id,
                sum(deployments) AS deployments,
                sum(failed_deployments) AS failed_deployments,
                sum(prs_merged) AS prs_merged,
                sum(commits) AS commits,
                sum(story_points_completed) AS story_points,
                count() AS days_tracked
            FROM dora_daily_metrics
            {where}
            GROUP BY project_id
            ORDER BY deployments DESC
        """
        dora_rows = ch.execute_query(dora_q)

        # Event counts by type
        evt_where = f"WHERE timestamp >= now() - INTERVAL {days} DAY"
        if proj:
            evt_where += f" AND project_id = '{proj}'"

        evt_q = f"""
            SELECT
                project_id,
                countIf(event_type='commit') AS commits,
                countIf(event_type='pr_merged') AS prs_merged,
                countIf(event_type='pr_reviewed') AS prs_reviewed,
                countIf(event_type='deploy') AS deploys,
                count() AS total_events,
                uniq(actor_id) AS unique_contributors
            FROM events
            {evt_where}
            GROUP BY project_id
        """
        evt_rows = ch.execute_query(evt_q)

        # Developer-level activity
        dev_q = f"""
            SELECT
                actor_id,
                count() AS total_events,
                countIf(event_type='commit') AS commits,
                countIf(event_type='deploy') AS deploys,
                groupUniqArray(project_id) AS projects
            FROM events
            {evt_where}
            GROUP BY actor_id
            ORDER BY total_events DESC
        """
        dev_rows = ch.execute_query(dev_q)

        current = {
            "period_days": days,
            "dora": _safe_serialise(dora_rows),
            "events_by_project": _safe_serialise(evt_rows),
            "developer_activity": _safe_serialise(dev_rows),
        }
        logger.info(f"Current metrics: {len(dora_rows)} projects DORA, "
                     f"{len(evt_rows)} projects events, {len(dev_rows)} devs")
        return {"current_metrics": current}

    except Exception as e:
        logger.error(f"Failed to fetch current metrics: {e}")
        return {"current_metrics": {"error": str(e)}, "status": "error"}


# ============================================================================
# Node 2: Fetch baseline metrics
# ============================================================================

def fetch_baseline_node(state: AnomalyState) -> dict:
    """Fetch historical baseline for comparison."""
    logger.info(f"Fetching baseline metrics (last {state['days_baseline']} days)")

    try:
        ch = get_clickhouse_client()
        days = int(state["days_baseline"])
        proj = state.get("project_id")

        where = f"WHERE date >= today() - {days}"
        if proj:
            where += f" AND project_id = '{proj}'"

        # Per-project weekly averages as baseline
        baseline_q = f"""
            SELECT
                project_id,
                avg(deployments) AS avg_daily_deployments,
                avg(failed_deployments) AS avg_daily_failed,
                avg(prs_merged) AS avg_daily_prs,
                avg(commits) AS avg_daily_commits,
                avg(story_points_completed) AS avg_daily_sp,
                count() AS days_tracked,
                sum(deployments) AS total_deployments,
                sum(commits) AS total_commits,
                sum(prs_merged) AS total_prs
            FROM dora_daily_metrics
            {where}
            GROUP BY project_id
        """
        rows = ch.execute_query(baseline_q)

        # Developer baseline
        evt_where = f"WHERE timestamp >= now() - INTERVAL {days} DAY"
        if proj:
            evt_where += f" AND project_id = '{proj}'"

        dev_base_q = f"""
            SELECT
                actor_id,
                count() / {days} * 7 AS avg_weekly_events,
                countIf(event_type='commit') / {days} * 7 AS avg_weekly_commits,
                countIf(event_type='deploy') / {days} * 7 AS avg_weekly_deploys
            FROM events
            {evt_where}
            GROUP BY actor_id
        """
        dev_rows = ch.execute_query(dev_base_q)

        baseline = {
            "period_days": days,
            "project_baselines": _safe_serialise(rows),
            "developer_baselines": _safe_serialise(dev_rows),
        }
        logger.info(f"Baseline: {len(rows)} project baselines, {len(dev_rows)} dev baselines")
        return {"baseline_metrics": baseline}

    except Exception as e:
        logger.error(f"Failed to fetch baseline: {e}")
        return {"baseline_metrics": {"error": str(e)}, "status": "error"}


# ============================================================================
# Node 3: Detect anomalies (LLM reasoning)
# ============================================================================

def detect_anomalies_node(state: AnomalyState) -> dict:
    """Use LLM to compare current vs baseline and identify anomalies."""
    logger.info("Detecting anomalies via LLM reasoning...")

    if state.get("status") == "error":
        return {"anomalies": [], "status": "error"}

    config = get_config()
    llm = ChatOpenAI(
        model=config.featherless.model_analytics,  # Llama 3.1 70B
        base_url=config.featherless.base_url,
        api_key=config.featherless.api_key,
        temperature=0.2,
    )

    prompt = f"""You are an engineering metrics anomaly detector.

Compare the CURRENT metrics (last {state['days_current']} days) against the BASELINE (last {state['days_baseline']} days).
Identify any significant anomalies — deviations that suggest problems or noteworthy changes.

CURRENT METRICS:
{json.dumps(state['current_metrics'], indent=2, default=str)[:3000]}

BASELINE METRICS:
{json.dumps(state['baseline_metrics'], indent=2, default=str)[:3000]}

For each anomaly found, provide:
1. metric_name: Which metric is anomalous
2. project_id: Which project (or "all" if org-wide)
3. direction: "increase" or "decrease"
4. severity: "low", "medium", "high", or "critical"
5. description: What the anomaly is
6. current_value: The current value
7. baseline_value: The baseline value

Respond with a JSON array of anomaly objects. If no anomalies are found, return an empty array [].
IMPORTANT: Return ONLY the JSON array, no other text.
"""

    try:
        log_llm_call(logger, config.featherless.model_analytics, prompt_preview=prompt[:200])
        response = llm.invoke([SystemMessage(content="You detect anomalies in engineering metrics."),
                               HumanMessage(content=prompt)])
        text = response.content.strip()
        
        # Parse JSON
        anomalies = _parse_json_array(text)
        
        status = "anomalies_found" if anomalies else "ok"
        logger.info(f"Anomaly detection complete: {len(anomalies)} anomalies found")
        for a in anomalies:
            logger.info(f"  🔴 {a.get('severity', '?').upper()}: {a.get('description', 'Unknown')[:80]}")

        return {"anomalies": anomalies, "status": status}

    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        return {"anomalies": [], "status": "error"}


# ============================================================================
# Node 4: Investigate root causes
# ============================================================================

def investigate_node(state: AnomalyState) -> dict:
    """Cross-reference anomalies with developer and project data to find root causes."""
    anomalies = state.get("anomalies", [])
    if not anomalies:
        return {"investigation": "No anomalies to investigate."}

    logger.info(f"Investigating root causes for {len(anomalies)} anomalies...")

    # Gather context from PostgreSQL
    try:
        pg = get_postgres_client()

        # Get developer info and project assignments
        dev_context = pg.execute_query("""
            SELECT e.full_name, e.email, e.role, e.title, t.name AS team_name,
                   array_agg(DISTINCT p.name) AS assigned_projects
            FROM employees e
            LEFT JOIN teams t ON e.team_id = t.id
            LEFT JOIN project_assignments pa ON pa.employee_id = e.id
            LEFT JOIN projects p ON pa.project_id = p.id
            WHERE e.active = true
            GROUP BY e.id, e.full_name, e.email, e.role, e.title, t.name
        """)

        project_context = pg.execute_query("""
            SELECT p.name, p.status, p.priority,
                   count(pa.employee_id) AS assigned_developers
            FROM projects p
            LEFT JOIN project_assignments pa ON pa.project_id = p.id
            GROUP BY p.id, p.name, p.status, p.priority
        """)
    except Exception as e:
        logger.error(f"Failed to load context from PostgreSQL: {e}")
        dev_context = []
        project_context = []

    config = get_config()
    llm = ChatOpenAI(
        model=config.featherless.model_primary,  # Qwen 72B for complex reasoning
        base_url=config.featherless.base_url,
        api_key=config.featherless.api_key,
        temperature=0.3,
    )

    prompt = f"""You are an engineering root cause investigator.

ANOMALIES DETECTED:
{json.dumps(anomalies, indent=2, default=str)[:2000]}

DEVELOPER CONTEXT (active employees with assignments):
{json.dumps(dev_context, indent=2, default=str)[:2000]}

PROJECT CONTEXT:
{json.dumps(project_context, indent=2, default=str)[:1500]}

DEVELOPER ACTIVITY (current period):
{json.dumps(state['current_metrics'].get('developer_activity', []), indent=2, default=str)[:1500]}

For each anomaly, investigate the root cause:
1. Cross-reference the metrics with developer assignments and activity
2. Look for patterns: developers with low activity on affected projects, team allocation issues, blocked work
3. Generate a hypothesis for WHY the anomaly occurred
4. Suggest specific actions to resolve

Be specific — name developers, projects, and teams when relevant.
"""

    try:
        log_llm_call(logger, config.featherless.model_primary, prompt_preview=prompt[:200])
        response = llm.invoke([
            SystemMessage(content="You investigate root causes of engineering anomalies."),
            HumanMessage(content=prompt),
        ])
        investigation = response.content.strip()
        logger.info(f"Root cause investigation complete ({len(investigation)} chars)")
        return {"investigation": investigation}

    except Exception as e:
        logger.error(f"Investigation failed: {e}")
        return {"investigation": f"Investigation failed: {e}"}


# ============================================================================
# Node 5: Generate alert
# ============================================================================

def generate_alert_node(state: AnomalyState) -> dict:
    """Generate a structured alert with recommendations."""
    anomalies = state.get("anomalies", [])
    if not anomalies:
        return {"alert_text": "✅ No anomalies detected — all metrics within normal ranges."}

    config = get_config()
    llm = ChatOpenAI(
        model=config.featherless.model_primary,
        base_url=config.featherless.base_url,
        api_key=config.featherless.api_key,
        temperature=0.4,
    )

    # Determine overall severity
    severities = [a.get("severity", "low") for a in anomalies]
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_sev = max(severities, key=lambda s: severity_order.get(s, 0))
    sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(max_sev, "⚪")

    prompt = f"""Generate a professional engineering anomaly alert.

ANOMALIES:
{json.dumps(anomalies, indent=2, default=str)[:2000]}

ROOT CAUSE INVESTIGATION:
{state.get('investigation', 'Not available')[:2000]}

Format the alert as:
1. Header with severity emoji and affected area
2. Summary of what was detected
3. Root cause hypothesis (be specific — name developers, projects)
4. Recommended actions (numbered, actionable)
5. Metrics comparison table (current vs baseline)

Use this severity: {sev_emoji} {max_sev.upper()}
Keep it concise but actionable. Max 500 words.
"""

    try:
        log_llm_call(logger, config.featherless.model_primary, prompt_preview=prompt[:200])
        response = llm.invoke([
            SystemMessage(content="You write clear, actionable engineering alerts."),
            HumanMessage(content=prompt),
        ])
        alert = response.content.strip()
        logger.info(f"Alert generated ({len(alert)} chars, severity={max_sev})")
        return {"alert_text": alert}

    except Exception as e:
        logger.error(f"Alert generation failed: {e}")
        return {"alert_text": f"Alert generation failed: {e}"}


# ============================================================================
# Node 6: Evaluate alert quality (self-check)
# ============================================================================

def evaluate_alert_node(state: AnomalyState) -> dict:
    """Self-evaluate the alert quality using LLM."""
    alert = state.get("alert_text", "")
    if not alert or state.get("status") == "ok":
        return {"quality_score": 1.0, "quality_feedback": "No alert needed."}

    config = get_config()
    llm = ChatOpenAI(
        model=config.featherless.model_fast,  # Hermes 3 8B for fast eval
        base_url=config.featherless.base_url,
        api_key=config.featherless.api_key,
        temperature=0.1,
    )

    prompt = f"""Evaluate this engineering alert for quality.

ALERT:
{alert[:2000]}

ANOMALIES IT SHOULD COVER:
{json.dumps(state.get('anomalies', []), indent=2, default=str)[:1000]}

Score from 0.0 to 1.0 on these criteria:
- Completeness: Does it cover all anomalies?
- Specificity: Does it name specific developers/projects/teams?
- Actionability: Are the recommendations concrete and actionable?
- Clarity: Is it clear and well-structured?

Respond with ONLY a JSON object:
{{"score": 0.85, "feedback": "Your feedback here"}}
"""

    try:
        log_llm_call(logger, config.featherless.model_fast, prompt_preview=prompt[:200])
        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()

        parsed = _parse_json_object(text)
        score = float(parsed.get("score", 0.5))
        feedback = parsed.get("feedback", "No feedback")

        logger.info(f"Alert quality: {score:.2f} — {feedback[:80]}")
        return {"quality_score": score, "quality_feedback": feedback}

    except Exception as e:
        logger.error(f"Alert evaluation failed: {e}")
        return {"quality_score": 0.5, "quality_feedback": f"Evaluation failed: {e}"}


# ============================================================================
# Node 7: Refine alert (on low quality)
# ============================================================================

def refine_alert_node(state: AnomalyState) -> dict:
    """Refine the alert based on quality feedback."""
    logger.info(f"Refining alert (attempt {state.get('refine_count', 0) + 1})")

    config = get_config()
    llm = ChatOpenAI(
        model=config.featherless.model_primary,
        base_url=config.featherless.base_url,
        api_key=config.featherless.api_key,
        temperature=0.4,
    )

    prompt = f"""Improve this engineering alert based on the feedback.

CURRENT ALERT:
{state.get('alert_text', '')[:2000]}

QUALITY FEEDBACK:
{state.get('quality_feedback', 'No specific feedback')}

ANOMALIES:
{json.dumps(state.get('anomalies', []), indent=2, default=str)[:1500]}

INVESTIGATION:
{state.get('investigation', '')[:1500]}

Address the feedback and improve the alert. Keep max 500 words.
"""

    try:
        log_llm_call(logger, config.featherless.model_primary, prompt_preview=prompt[:200])
        response = llm.invoke([
            SystemMessage(content="Improve the alert based on feedback."),
            HumanMessage(content=prompt),
        ])
        refined = response.content.strip()
        logger.info(f"Alert refined ({len(refined)} chars)")
        return {
            "alert_text": refined,
            "refine_count": state.get("refine_count", 0) + 1,
        }

    except Exception as e:
        logger.error(f"Alert refinement failed: {e}")
        return {"refine_count": state.get("refine_count", 0) + 1}


# ============================================================================
# Routing
# ============================================================================

def route_after_detection(state: AnomalyState) -> str:
    """Route after anomaly detection."""
    if state.get("status") == "error":
        return "done"
    if not state.get("anomalies"):
        return "done"
    return "investigate"


def route_after_evaluation(state: AnomalyState) -> str:
    """Route after quality evaluation — refine if score < 0.7 and retries left."""
    score = state.get("quality_score", 1.0)
    retries = state.get("refine_count", 0)
    if score >= 0.7 or retries >= MAX_REFINE_RETRIES:
        return "done"
    return "refine"


# ============================================================================
# Graph Builder
# ============================================================================

_graph = None


def get_anomaly_graph():
    """Build and cache the anomaly detection LangGraph."""
    global _graph
    if _graph is not None:
        return _graph

    logger.info("Building anomaly detection sub-graph...")
    workflow = StateGraph(AnomalyState)

    workflow.add_node("fetch_current", fetch_current_node)
    workflow.add_node("fetch_baseline", fetch_baseline_node)
    workflow.add_node("detect", detect_anomalies_node)
    workflow.add_node("investigate", investigate_node)
    workflow.add_node("generate_alert", generate_alert_node)
    workflow.add_node("evaluate", evaluate_alert_node)
    workflow.add_node("refine", refine_alert_node)

    # Flow
    workflow.set_entry_point("fetch_current")
    workflow.add_edge("fetch_current", "fetch_baseline")
    workflow.add_edge("fetch_baseline", "detect")
    workflow.add_conditional_edges("detect", route_after_detection, {
        "investigate": "investigate",
        "done": END,
    })
    workflow.add_edge("investigate", "generate_alert")
    workflow.add_edge("generate_alert", "evaluate")
    workflow.add_conditional_edges("evaluate", route_after_evaluation, {
        "refine": "refine",
        "done": END,
    })
    workflow.add_edge("refine", "evaluate")

    _graph = workflow.compile()
    logger.info("✓ Anomaly detection graph compiled")
    return _graph


# ============================================================================
# Public API
# ============================================================================

def run_anomaly_detection(
    project_id: Optional[str] = None,
    days_current: int = 7,
    days_baseline: int = 30,
) -> dict:
    """
    Run the full anomaly detection pipeline.

    Args:
        project_id:    Optional project to scope analysis to.
        days_current:  Window for current metrics (default 7 days).
        days_baseline: Window for baseline comparison (default 30 days).

    Returns:
        dict with keys: anomalies, alert_text, quality_score, status, investigation
    """
    graph = get_anomaly_graph()

    initial_state: AnomalyState = {
        "project_id": project_id,
        "days_current": days_current,
        "days_baseline": days_baseline,
        "current_metrics": {},
        "baseline_metrics": {},
        "anomalies": [],
        "investigation": "",
        "alert_text": "",
        "quality_score": 0.0,
        "quality_feedback": "",
        "refine_count": 0,
        "status": "ok",
    }

    logger.info(f"🔍 Running anomaly detection (project={project_id or 'all'}, "
                f"current={days_current}d, baseline={days_baseline}d)")
    final_state = graph.invoke(initial_state)

    return {
        "anomalies": final_state.get("anomalies", []),
        "alert_text": final_state.get("alert_text", ""),
        "quality_score": final_state.get("quality_score", 0),
        "investigation": final_state.get("investigation", ""),
        "status": final_state.get("status", "ok"),
        "refine_count": final_state.get("refine_count", 0),
    }


# ============================================================================
# Helpers
# ============================================================================

def _safe_serialise(rows: list) -> list:
    """Safely serialise ClickHouse results to JSON-compatible dicts."""
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


def _parse_json_array(text: str) -> list:
    """Extract a JSON array from LLM output."""
    text = text.strip()
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Try to find JSON in markdown code block
    import re
    match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try to find bare array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _parse_json_object(text: str) -> dict:
    """Extract a JSON object from LLM output."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
