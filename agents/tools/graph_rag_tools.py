"""
Graph RAG Expert Discovery Tools  (Feature 3.3)
=================================================

LangChain @tool wrappers that expose the Graph RAG pipeline
to specialist agents.

Tools:
    find_expert_for_topic  — full pipeline: vector + graph + fusion + LLM explanation
    quick_expert_search    — lightweight: vector-only fast search (no LLM synthesis)
"""

from langchain_core.tools import tool
from agents.utils.logger import get_logger, log_tool_call

logger = get_logger(__name__, "GRAPH_RAG_TOOLS")


@tool
def find_expert_for_topic(query: str, limit: int = 5) -> str:
    """
    Find the best expert for a topic using Graph RAG (vector + knowledge graph fusion).

    Combines pgvector semantic similarity with Neo4j graph traversal
    (expertise, contributions, collaborations) to produce a ranked list
    of recommended experts with natural-language explanations.

    Args:
        query: Natural-language question, e.g.
               "Who can help debug the payment processing timeout?"
               "Find a Kubernetes expert"
               "Who knows about React TypeScript?"
        limit: Maximum number of experts to return (default 5)

    Returns:
        A formatted expert discovery report with ranked recommendations.
    """
    log_tool_call(logger, "find_expert_for_topic", {"query": query, "limit": limit})

    from agents.pipelines.graph_rag_pipeline import find_expert

    result = find_expert(query, limit=limit)

    report = result.get("report", "No results")
    ranking = result.get("fused_ranking", [])
    status = result.get("status", "unknown")

    # Append metadata footer
    footer_parts = [
        f"\n\n---\n_Graph RAG | Status: {status}",
        f"| Candidates evaluated: {len(ranking)}",
    ]
    if ranking:
        top = ranking[0]
        footer_parts.append(
            f"| Top match: {top['name']} (combined={top['combined_score']})"
        )
    footer_parts.append("_")

    return report + " ".join(footer_parts)


@tool
def quick_expert_search(skills: str, limit: int = 5) -> str:
    """
    Fast skill-based expert search using vector similarity only (no graph traversal or LLM synthesis).

    Use this when you need a quick list of developers matching certain skills
    without the full Graph RAG pipeline overhead.

    Args:
        skills: Skills or expertise to search for, e.g. "Python machine learning", "Kubernetes AWS"
        limit: Maximum number of results (default 5)

    Returns:
        A formatted list of matching developers with similarity scores.
    """
    log_tool_call(logger, "quick_expert_search", {"skills": skills, "limit": limit})

    from agents.tools.vector_tools import find_developer_by_skills

    results = find_developer_by_skills.invoke({"skills": skills, "limit": limit})

    if not results or (len(results) == 1 and "error" in results[0]):
        return f"No developers found matching: {skills}"

    lines = [f"**Quick Expert Search: {skills}**\n"]
    for i, dev in enumerate(results):
        name = dev.get("full_name", "Unknown")
        sim = dev.get("similarity", 0)
        title = dev.get("title", "")
        team = dev.get("team_name", "")
        lines.append(f"{i+1}. **{name}** — {title} ({team}) | Similarity: {sim}")

    lines.append(f"\n_Vector-only search | {len(results)} matches_")
    return "\n".join(lines)


# Export
GRAPH_RAG_TOOLS = [find_expert_for_topic, quick_expert_search]
