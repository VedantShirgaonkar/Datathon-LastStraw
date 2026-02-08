"""
RAG Tools — Exposes the Agentic RAG pipeline as a LangChain tool.
"""

from __future__ import annotations

from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call

logger = get_logger(__name__, "RAG_TOOLS")


@tool
def rag_search(question: str) -> str:
    """
    Intelligent semantic search with self-correction.
    Uses the Agentic RAG pipeline to:
    1. Retrieve relevant documents via pgvector
    2. Grade documents for relevance
    3. Rewrite query if results are poor
    4. Generate a grounded answer
    5. Self-check for hallucination

    Use this for complex questions about developers, projects, or skills
    that need reasoning across multiple documents.

    Args:
        question: The user's natural language question.

    Returns:
        A grounded answer synthesized from relevant documents.
    """
    log_tool_call(logger, "rag_search", {"question": question[:100]})

    from agents.pipelines.rag_pipeline import rag_query

    result = rag_query(question)

    # Build a rich response
    parts = [result["answer"]]

    n_docs = len(result.get("relevant_docs", []))
    retries = result.get("retry_count", 0)
    hallucinated = result.get("is_hallucinated", False)

    meta = []
    if n_docs:
        meta.append(f"Sources: {n_docs} documents")
    if retries:
        meta.append(f"Query rewrites: {retries}")
    if hallucinated:
        meta.append("⚠️ Some claims may not be fully supported by sources")

    if meta:
        parts.append("\n\n---\n_" + " | ".join(meta) + "_")

    return "".join(parts)


RAG_TOOLS = [rag_search]
