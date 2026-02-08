"""
Resource Planning Specialist Agent
Focuses on project status, team capacity, developer workload, and resource allocation.
Default model: Qwen 2.5 72B (can be overridden by multi-model router).
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.utils.model_router import get_llm
from agents.tools.postgres_tools import get_project, list_projects, get_developer_workload, list_developers
from agents.tools.prep_tools import PREP_TOOLS

logger = get_logger(__name__, "RESOURCE_AGENT")

# Subset of tools relevant to resource planning + 1:1 prep
RESOURCE_TOOLS = [get_project, list_projects, get_developer_workload, list_developers] + PREP_TOOLS

SYSTEM_PROMPT = """You are the Resource Planning Specialist.
Your goal is to optimize team allocation and ensure project delivery.

Key Responsibilities:
1. Monitoring project status and risks.
2. Analyzing developer workload and capacity.
3. Identifying resource bottlenecks or overallocation (>100%).
4. Recommending resource adjustments.
5. **Preparing 1:1 meeting briefings** for managers.

You have access to:
- PostgreSQL tools for project/developer data.
- **prepare_one_on_one**: Generates a comprehensive 1:1 meeting briefing with activity data,
  workload analysis, collaboration patterns, and suggested talking points.
- **suggest_talking_points**: Generates focused talking points for specific discussion areas.

When a user asks to "prepare for a 1:1" or "meeting prep" for a specific developer,
use the prepare_one_on_one tool. For quick talking points, use suggest_talking_points.

When analyzing workload:
- Flag developers with >100% allocation.
- Suggest available developers (<80% allocation) for new tasks.
- Consider project priority when recommending resource shifts.

Be precise with numbers and percentages."""


def create_resource_agent(
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
):
    """
    Create the resource planning specialist agent.

    Args:
        model_override:  If provided, use this model instead of the default.
        temperature_override: If provided, use this temperature.
    """
    temperature = temperature_override if temperature_override is not None else 0.1
    
    llm = get_llm(model_override=model_override, temperature=temperature)
    logger.info(f"Creating Resource Agent with model: {llm.model_name}")
    
    agent = create_react_agent(
        model=llm,
        tools=RESOURCE_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent


# Singleton instance (default model only)
_resource_agent = None

def get_resource_agent():
    global _resource_agent
    if _resource_agent is None:
        _resource_agent = create_resource_agent()
    return _resource_agent
