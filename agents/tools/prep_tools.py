"""
1:1 Prep Tools (Feature 2.3)
==============================
LangChain tool wrapper for the 1:1 prep pipeline so specialist
agents can generate meeting briefings on demand.
"""

from __future__ import annotations

from langchain_core.tools import tool

from agents.utils.logger import get_logger

logger = get_logger(__name__, "PREP_TOOLS")


@tool
def prepare_one_on_one(developer_name: str, manager_context: str = "") -> str:
    """Prepare a 1:1 meeting briefing for a specific developer.

    Gathers their recent activity, project assignments, workload, and
    collaboration patterns, then synthesizes an actionable briefing
    with talking points and growth suggestions.

    Args:
        developer_name: Name or email of the developer to prepare for.
        manager_context: Optional notes or concerns from the manager.
    """
    from agents.pipelines.prep_pipeline import prepare_one_on_one as _run

    logger.info(f"Preparing 1:1 briefing for: {developer_name}")
    result = _run(
        developer_name=developer_name,
        manager_context=manager_context,
    )

    if result["status"] == "developer_not_found":
        return f"❌ Developer '{developer_name}' was not found in the system. Please check the name."

    if result["status"] == "error":
        # The briefing will contain the error message
        return result["briefing"]

    # Format output
    output = result["briefing"]

    # Append metadata footer
    dev = result.get("developer_info", {})
    tp = result.get("talking_points", [])
    output += (
        f"\n\n---\n"
        f"📊 **Briefing Metadata**\n"
        f"- Developer: {dev.get('full_name', developer_name)}\n"
        f"- Team: {dev.get('team_name', 'N/A')}\n"
        f"- Role: {dev.get('title', dev.get('role', 'N/A'))}\n"
        f"- Talking Points Extracted: {len(tp)}\n"
    )
    return output


@tool
def suggest_talking_points(developer_name: str, focus_area: str = "") -> str:
    """Generate focused talking points for a 1:1 meeting with a developer.

    Unlike the full briefing, this returns a concise list of discussion
    topics tailored to a specific focus area.

    Args:
        developer_name: Name or email of the developer.
        focus_area: Optional focus area, e.g. "career growth", "workload",
                    "blockers", "collaboration", "performance".
    """
    from agents.pipelines.prep_pipeline import prepare_one_on_one as _run

    logger.info(f"Generating talking points for {developer_name} "
                f"(focus: {focus_area or 'general'})")
    result = _run(
        developer_name=developer_name,
        manager_context=f"Focus area for this 1:1: {focus_area}" if focus_area else "",
    )

    if result["status"] != "ok":
        return f"Could not generate talking points for '{developer_name}'."

    points = result.get("talking_points", [])
    if not points:
        # Fall back to the full briefing
        return (
            f"Full briefing for {result.get('developer_info', {}).get('full_name', developer_name)}:\n\n"
            f"{result['briefing']}"
        )

    header = f"💬 **Talking Points for {result.get('developer_info', {}).get('full_name', developer_name)}**"
    if focus_area:
        header += f" (Focus: {focus_area})"
    lines = [header, ""]
    for i, point in enumerate(points, 1):
        lines.append(f"{i}. {point}")

    return "\n".join(lines)


# Export list for agent integration
PREP_TOOLS = [prepare_one_on_one, suggest_talking_points]
