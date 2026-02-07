"""
Developer Insights Specialist Agent
Focuses on developer profiles, skills, collaboration graphs, and knowledge expertise.
Uses Hermes 3 8B (Fast) for quick lookups and graph traversal.
"""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

from agents.utils.logger import get_logger
from agents.utils.config import get_config
from agents.tools.postgres_tools import get_developer, get_team, list_developers
from agents.tools.vector_tools import semantic_search, find_developer_by_skills
from agents.tools.neo4j_tools import get_collaborators, get_team_collaboration_graph, find_knowledge_experts

logger = get_logger(__name__, "INSIGHTS_AGENT")

# Combine relevant tools
INSIGHTS_TOOLS = [
    get_developer, get_team, list_developers,
    semantic_search, find_developer_by_skills,
    get_collaborators, get_team_collaboration_graph, find_knowledge_experts
]

SYSTEM_PROMPT = """You are the Developer Insights Specialist.
Your goal is to understand the people, skills, and relationships within the engineering organization.

Key Responsibilities:
1. Finding developers with specific skills or expertise.
2. Understanding team composition and collaboration patterns.
3. Identifying knowledge silos or key influencers.
4. Providing developer profiles.

You have access to:
- PostgreSQL tools for basic profile data.
- Vector search for skill matching.
- Neo4j tools for collaboration graphs.

When asked about "who knows X" or "who works with Y", use the graph and vector tools.
Be concise and focus on the human element."""

def create_insights_agent():
    """Create the insights specialist agent."""
    config = get_config()
    
    logger.info(f"Creating Insights Agent with model: {config.featherless.model_fast}")
    
    llm = ChatOpenAI(
        model=config.featherless.model_fast,
        api_key=config.featherless.api_key,
        base_url=config.featherless.base_url,
        temperature=0.1,
    )
    
    agent = create_react_agent(
        model=llm,
        tools=INSIGHTS_TOOLS,
        prompt=SYSTEM_PROMPT
    )
    
    return agent

# Singleton instance
_insights_agent = None

def get_insights_agent():
    global _insights_agent
    if _insights_agent is None:
        _insights_agent = create_insights_agent()
    return _insights_agent
