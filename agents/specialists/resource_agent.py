"""
Resource Planning Specialist Agent
Focuses on project status, team capacity, developer workload, and resource allocation.
Uses Qwen 2.5 72B for complex constraint reasoning and planning.
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.tools.postgres_tools import get_project, list_projects, get_developer_workload, list_developers

logger = get_logger(__name__, "RESOURCE_AGENT")

# Subset of tools relevant to resource planning
RESOURCE_TOOLS = [get_project, list_projects, get_developer_workload, list_developers]

SYSTEM_PROMPT = """You are the Resource Planning Specialist.
Your goal is to optimize team allocation and ensure project delivery.

Key Responsibilities:
1. Monitoring project status and risks.
2. analyzing developer workload and capacity.
3. Identifying resource bottlenecks or overallocation (>100%).
4. Recommend resource adjustments.

You have access to PostgreSQL tools to query project and developer allocation data.
When analyzing workload:
- Flag developers with >100% allocation.
- Suggest available developers (<80% allocation) for new tasks.
- Consider project priority when recommending resource shifts.

Be precise with numbers and percentages."""

def create_resource_agent():
    """Create the resource planning specialist agent."""
    config = get_config()
    
    logger.info(f"Creating Resource Agent with model: {config.featherless.model_primary}")
    
    llm = ChatOpenAI(
        model=config.featherless.model_primary,
        api_key=config.featherless.api_key,
        base_url=config.featherless.base_url,
        temperature=0.1,
    )
    
    agent = create_react_agent(
        model=llm,
        tools=RESOURCE_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent

# Singleton instance
_resource_agent = None

def get_resource_agent():
    global _resource_agent
    if _resource_agent is None:
        _resource_agent = create_resource_agent()
    return _resource_agent
