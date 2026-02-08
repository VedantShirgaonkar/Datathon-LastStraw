"""
Developer Insights Specialist Agent
Focuses on developer profiles, skills, collaboration graphs, and knowledge expertise.
Default model: Hermes 3 8B (can be overridden by multi-model router).
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.utils.model_router import get_llm
from agents.tools.postgres_tools import get_developer, get_team, list_developers
from agents.tools.vector_tools import semantic_search, find_developer_by_skills
from agents.tools.neo4j_tools import get_collaborators, get_team_collaboration_graph, find_knowledge_experts
from agents.tools.rag_tools import rag_search
from agents.tools.graph_rag_tools import GRAPH_RAG_TOOLS

logger = get_logger(__name__, "INSIGHTS_AGENT")

# Combine relevant tools (rag_search for complex multi-doc questions, graph RAG for expert discovery)
INSIGHTS_TOOLS = [
    get_developer, get_team, list_developers,
    semantic_search, find_developer_by_skills,
    get_collaborators, get_team_collaboration_graph, find_knowledge_experts,
    rag_search,
] + GRAPH_RAG_TOOLS

SYSTEM_PROMPT = """You are the Developer Insights Specialist.
Your goal is to understand the people, skills, and relationships within the engineering organization.

Key Responsibilities:
1. Finding developers with specific skills or expertise.
2. Understanding team composition and collaboration patterns.
3. Identifying knowledge silos or key influencers.
4. Providing developer profiles.
5. **Expert discovery** — finding the best person to help with a topic.

You have access to:
- PostgreSQL tools for basic profile data.
- Vector search (semantic_search, find_developer_by_skills) for skill matching.
- Neo4j tools for collaboration graphs.
- **rag_search** for complex questions needing multi-document reasoning with self-correction.
- **find_expert_for_topic** for full Graph RAG expert discovery (vector + knowledge graph fusion + LLM explanations). Use this for "who can help with X?" or "find an expert in Y".
- **quick_expert_search** for fast skill-based developer matching (vector-only, no LLM overhead).

When asked "who can help with X?" or "find an expert", prefer **find_expert_for_topic** (Graph RAG).
When asked about "who knows X" or general skill matching, use find_developer_by_skills or quick_expert_search.
For simple profile lookups, use get_developer or list_developers.
Be concise and focus on the human element."""


def create_insights_agent(
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
):
    """
    Create the insights specialist agent.

    Args:
        model_override:  If provided, use this model instead of the default.
        temperature_override: If provided, use this temperature.
    """
    temperature = temperature_override if temperature_override is not None else 0.1
    
    llm = get_llm(model_override=model_override, temperature=temperature)
    logger.info(f"Creating Insights Agent with model: {llm.model_name}")
    
    agent = create_react_agent(
        model=llm,
        tools=INSIGHTS_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent


# Singleton instance (default model only)
_insights_agent = None

def get_insights_agent():
    global _insights_agent
    if _insights_agent is None:
        _insights_agent = create_insights_agent()
    return _insights_agent
