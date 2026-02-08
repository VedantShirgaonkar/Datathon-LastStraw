"""
DORA Metrics Specialist Agent
Focuses on deployment frequency, lead time, change failure rate, and MTTR.
Default model: Llama 3.1 70B (can be overridden by multi-model router).
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.utils.model_router import get_llm
from agents.tools.clickhouse_tools import CLICKHOUSE_TOOLS
from agents.tools.anomaly_tools import ANOMALY_TOOLS
from agents.tools.nl_query_tools import NL_QUERY_TOOLS

logger = get_logger(__name__, "DORA_AGENT")

DORA_TOOLS = CLICKHOUSE_TOOLS + ANOMALY_TOOLS + NL_QUERY_TOOLS

SYSTEM_PROMPT = """You are the DORA Metrics Specialist.
Your goal is to analyze engineering performance using the four key DORA metrics:
1. Deployment Frequency (How often code is deployed)
2. Lead Time for Changes (Time from commit to deployment)
3. Change Failure Rate (Percentage of deployments causing failure)
4. Mean Time to Recovery (Time to restore service after failure)

You have access to ClickHouse tools to query events and pre-calculated metrics.
You also have an anomaly detection tool that can identify metric anomalies,
investigate root causes across multiple data sources, and generate alerts.
You also have a **natural_language_query** tool that can generate and execute
SQL queries from plain English questions — use it for ad-hoc or complex queries.

When analyzing:
- Always look for trends (improving/degrading).
- Compare against industry standards (Elite, High, Medium, Low performers).
- Provide actionable recommendations to improve specific metrics.
- Use detect_anomalies when asked about problems, drops, issues, or anything unusual.

If you cannot answer a query with your tools, state clearly what data is missing."""


def create_dora_agent(
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
):
    """
    Create the DORA metrics specialist agent.

    Args:
        model_override:  If provided, use this model instead of the default.
        temperature_override: If provided, use this temperature.
    """
    temperature = temperature_override if temperature_override is not None else 0.1
    
    llm = get_llm(model_override=model_override, temperature=temperature)
    logger.info(f"Creating DORA Agent with model: {llm.model_name}")
    
    agent = create_react_agent(
        model=llm,
        tools=DORA_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent


# Singleton instance (default model only)
_dora_agent = None

def get_dora_agent():
    global _dora_agent
    if _dora_agent is None:
        _dora_agent = create_dora_agent()
    return _dora_agent
