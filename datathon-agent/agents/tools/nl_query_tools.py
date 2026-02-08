"""
NL→SQL/Cypher Tools (Feature 1.3)
===================================
LangChain tool wrapper for the NL→Query pipeline so specialist
agents can translate natural language questions into database queries.
"""

from __future__ import annotations

from langchain_core.tools import tool

from agents.utils.logger import get_logger

logger = get_logger(__name__, "NL_QUERY_TOOLS")


@tool
def natural_language_query(question: str) -> str:
    """Answer a natural language question by automatically generating and executing a database query.

    Translates the question into SQL (for PostgreSQL or ClickHouse) or Cypher (for Neo4j),
    validates the query, executes it, and returns a natural language summary of the results.
    Self-corrects if the query fails.

    Use this for questions like:
    - "What's the average deployment frequency for each project?"
    - "Which developers have the highest allocation percentage?"
    - "How many commits were made last week by each team?"

    Args:
        question: A natural language question about engineering data.
    """
    from agents.pipelines.nl_query_pipeline import nl_query

    logger.info(f"NL→Query tool invoked: {question[:100]}")
    result = nl_query(question=question)

    # Format output
    output = result.get("summary", "No results")

    # Append metadata
    output += (
        f"\n\n---\n"
        f"📊 **Query Details**\n"
        f"- Database: {result.get('target_db', 'N/A')}\n"
        f"- Language: {result.get('query_language', 'N/A').upper()}\n"
        f"- Rows returned: {len(result.get('query_results', []))}\n"
        f"- Retries: {result.get('retry_count', 0)}\n"
        f"- Query: `{result.get('generated_query', 'N/A')[:200]}`\n"
    )
    return output


# Export list for agent integration
NL_QUERY_TOOLS = [natural_language_query]
