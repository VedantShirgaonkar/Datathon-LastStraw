"""
DORA Metrics Specialist Agent
Focuses on deployment frequency, lead time, change failure rate, and MTTR.
Uses Llama 3.1 70B for robust data analysis and structured reasoning.
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.tools.clickhouse_tools import CLICKHOUSE_TOOLS

logger = get_logger(__name__, "DORA_AGENT")

SYSTEM_PROMPT = """You are the DORA Metrics Specialist.
Your goal is to analyze engineering performance using the four key DORA metrics:
1. Deployment Frequency (How often code is deployed)
2. Lead Time for Changes (Time from commit to deployment)
3. Change Failure Rate (Percentage of deployments causing failure)
4. Mean Time to Recovery (Time to restore service after failure)

You have access to ClickHouse tools to query events and pre-calculated metrics.
When analyzing:
- Always look for trends (improving/degrading).
- Compare against industry standards (Elite, High, Medium, Low performers).
- Provide actionable recommendations to improve specific metrics.

If you cannot answer a query with your tools, state clearly what data is missing."""

def create_dora_agent():
    """Create the DORA metrics specialist agent."""
    config = get_config()
    
    logger.info(f"Creating DORA Agent with model: {config.featherless.model_analytics}")
    
    llm = ChatOpenAI(
        model=config.featherless.model_analytics,
        api_key=config.featherless.api_key,
        base_url=config.featherless.base_url,
        temperature=0.1,
    )
    
    agent = create_react_agent(
        model=llm,
        tools=CLICKHOUSE_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent

# Singleton instance
_dora_agent = None

def get_dora_agent():
    global _dora_agent
    if _dora_agent is None:
        _dora_agent = create_dora_agent()
    return _dora_agent
