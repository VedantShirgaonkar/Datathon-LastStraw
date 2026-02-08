"""
Anomaly Detection Tool
Wraps the anomaly pipeline for use by specialist agents (primarily DORA_Pro).
"""

from typing import Optional
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call

logger = get_logger(__name__, "ANOMALY_TOOLS")


@tool
def detect_anomalies(
    project_id: Optional[str] = None,
    days_current: int = 7,
    days_baseline: int = 30,
) -> str:
    """
    Run anomaly detection on engineering metrics.
    
    Compares current metrics against historical baselines using AI reasoning,
    investigates root causes across multiple data sources, and generates
    actionable alerts with severity scores and recommendations.
    
    Args:
        project_id:    Optional project to scope analysis to (e.g. 'proj-api').
                       Analyzes all projects if omitted.
        days_current:  Window for current metrics in days (default 7).
        days_baseline: Window for historical baseline in days (default 30).
    
    Returns:
        A formatted anomaly report with root cause analysis and recommendations.
    """
    from agents.pipelines.anomaly_pipeline import run_anomaly_detection

    logger.info(f"Anomaly detection tool invoked (project={project_id}, "
                f"current={days_current}d, baseline={days_baseline}d)")

    try:
        result = run_anomaly_detection(
            project_id=project_id,
            days_current=days_current,
            days_baseline=days_baseline,
        )

        status = result.get("status", "ok")
        anomalies = result.get("anomalies", [])
        alert = result.get("alert_text", "")
        quality = result.get("quality_score", 0)
        refine_count = result.get("refine_count", 0)

        # Build response
        parts = []
        if status == "ok" and not anomalies:
            parts.append("✅ No anomalies detected — all metrics are within normal ranges.")
        elif alert:
            parts.append(alert)
        else:
            parts.append(f"⚠️ Anomaly detection completed with status: {status}")
            if anomalies:
                parts.append(f"\nFound {len(anomalies)} anomalie(s):")
                for a in anomalies:
                    sev = a.get("severity", "?")
                    desc = a.get("description", "Unknown")
                    parts.append(f"  - [{sev.upper()}] {desc}")

        # Metadata footer
        parts.append(f"\n---\n📊 Analysis: {len(anomalies)} anomalies | "
                     f"Quality: {quality:.0%} | Refinements: {refine_count}")

        response = "\n".join(parts)
        log_tool_call(logger, "detect_anomalies",
                      {"project": project_id, "days": days_current},
                      f"{len(anomalies)} anomalies, quality={quality:.0%}")
        return response

    except Exception as e:
        log_tool_call(logger, "detect_anomalies", {"project": project_id}, error=e)
        return f"Error running anomaly detection: {e}"


ANOMALY_TOOLS = [detect_anomalies]
