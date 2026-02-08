"""
Agentic RAG Pipeline (Feature 1.1)
Self-Reflective Retrieval-Augmented Generation with:
  1. Query embedding & pgvector retrieval (top-k)
  2. Document relevance grading (fast LLM)
  3. Query rewriting on poor results (retry loop)
  4. Grounded answer generation (strong LLM)
  5. Hallucination self-check (fast LLM)

Graph:
  START → retrieve → grade → [relevant?]
      ├── yes → generate → hallucination_check → [grounded?]
      │       ├── yes → END
      │       └── no  → rewrite → retrieve (loop)
      └── no  → rewrite → retrieve (loop)
"""

from __future__ import annotations

import json
from typing import TypedDict, List

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START

from agents.utils.logger import get_logger, PhaseLogger, log_llm_call
from agents.utils.config import get_config
from agents.utils.model_router import get_llm
from agents.tools.embedding_tools import get_embedding
from agents.utils.db_clients import get_postgres_client

logger = get_logger(__name__, "RAG_PIPELINE")

# Maximum retrieval-rewrite loop iterations
MAX_RETRIES = 2


def _get_pipeline_llm(temperature: float = 0.0):
    """Get LLM for RAG pipeline using centralized routing."""
    return get_llm(temperature=temperature)


# ============================================================================
# RAG State
# ============================================================================

class RAGState(TypedDict):
    """State for the self-reflective RAG pipeline."""
    original_query: str                 # User's raw question
    current_query: str                  # May be rewritten
    retrieved_docs: list[dict]          # Documents from pgvector
    relevant_docs: list[dict]           # After grading
    answer: str                         # Generated answer
    is_hallucinated: bool               # Hallucination check result
    retry_count: int                    # Number of rewrite iterations
    status: str                         # Pipeline status for routing


# ============================================================================
# Node: Retrieve from pgvector
# ============================================================================

def retrieve_node(state: RAGState) -> dict:
    """Embed the current query and retrieve top-k from pgvector."""
    query = state["current_query"]
    logger.info(f"Retrieving for: {query[:80]}...")

    embedding = get_embedding(query)
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

    sql = """
        SELECT
            e.id,
            e.source_table,
            e.source_id,
            e.title,
            e.content,
            e.metadata,
            1 - (e.embedding <=> %s::vector) AS similarity
        FROM embeddings e
        ORDER BY e.embedding <=> %s::vector
        LIMIT 8
    """

    pg = get_postgres_client()
    rows = pg.execute_query(sql, (vec_literal, vec_literal))

    docs = []
    for r in rows:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        docs.append({
            "id": str(r.get("id", "")),
            "entity_type": r.get("source_table", ""),
            "entity_id": str(r.get("source_id", "")),
            "title": r.get("title", ""),
            "content": r.get("content", ""),
            "similarity": float(r.get("similarity", 0)),
            "metadata": meta,
        })

    if docs:
        logger.info(f"Retrieved {len(docs)} docs (top sim: {docs[0]['similarity']:.3f})")
    else:
        logger.warning("No documents retrieved")

    return {"retrieved_docs": docs}


# ============================================================================
# Node: Grade Documents for Relevance
# ============================================================================

_GRADING_PROMPT = """You are a relevance grader. Given a user question and a retrieved document,
decide if the document is relevant to answering the question.

Respond with ONLY a JSON object: {{"relevant": true}} or {{"relevant": false}}

User question: {question}

Document:
{document}
"""


def grade_documents_node(state: RAGState) -> dict:
    """Use a fast LLM to grade each retrieved document for relevance."""
    query = state["current_query"]
    docs = state["retrieved_docs"]

    if not docs:
        logger.warning("No documents to grade")
        return {"relevant_docs": [], "status": "no_docs"}

    grader_llm = _get_pipeline_llm(temperature=0.0)

    relevant = []
    for doc in docs:
        # Skip very low similarity docs
        if doc["similarity"] < 0.25:
            continue

        prompt = _GRADING_PROMPT.format(
            question=query,
            document=doc["content"][:1500],
        )

        try:
            resp = grader_llm.invoke([HumanMessage(content=prompt)])
            text = resp.content.strip()

            log_llm_call(logger, model="Hermes-3-8B (grader)", prompt_preview=query[:80])

            if '"relevant": true' in text.lower() or '"relevant":true' in text.lower():
                relevant.append(doc)
                logger.debug(f"  ✅ Relevant: {doc['entity_type']}/{doc['entity_id']} (sim={doc['similarity']:.3f})")
            else:
                logger.debug(f"  ❌ Irrelevant: {doc['entity_type']}/{doc['entity_id']} (sim={doc['similarity']:.3f})")
        except Exception as e:
            logger.warning(f"Grading failed for {doc['entity_id']}: {e}")
            # Fallback: include docs with decent similarity
            if doc["similarity"] >= 0.40:
                relevant.append(doc)

    status = "relevant_found" if relevant else "no_relevant"
    logger.info(f"Grading: {len(relevant)}/{len(docs)} relevant (status={status})")
    return {"relevant_docs": relevant, "status": status}


# ============================================================================
# Node: Rewrite Query
# ============================================================================

_REWRITE_PROMPT = """You are a query rewriter for a developer intelligence system.
The original query did not retrieve relevant results. Rewrite it to be more specific
and likely to match employee profiles or project descriptions in the database.

The database contains:
- Employee profiles (name, role, team, skills, title)
- Project descriptions (name, tech stack, status, team members)

Original query: {query}

Rewrite the query to improve retrieval. Output ONLY the rewritten query text, nothing else."""


def rewrite_query_node(state: RAGState) -> dict:
    """Rewrite the query for better retrieval."""
    query = state["current_query"]
    retry_count = state.get("retry_count", 0)

    logger.info(f"Rewriting query (attempt {retry_count + 1}/{MAX_RETRIES})")

    rewriter = _get_pipeline_llm(temperature=0.3)

    prompt = _REWRITE_PROMPT.format(query=query)
    resp = rewriter.invoke([HumanMessage(content=prompt)])
    new_query = resp.content.strip().strip('"').strip("'")

    log_llm_call(logger, model="Hermes-3-8B (rewriter)", prompt_preview=query[:80])
    logger.info(f"Rewritten: '{query}' → '{new_query}'")

    return {
        "current_query": new_query,
        "retry_count": retry_count + 1,
        "status": "rewritten",
    }


# ============================================================================
# Node: Generate Answer
# ============================================================================

_GENERATE_PROMPT = """You are an engineering intelligence assistant. Answer the user's question
using ONLY the provided context documents. Be specific, cite names and data.
If the context is insufficient, say so honestly — never make up information.

Context Documents:
{context}

User Question: {question}

Provide a clear, well-structured answer:"""


def generate_answer_node(state: RAGState) -> dict:
    """Generate an answer grounded in the relevant documents."""
    query = state["original_query"]
    docs = state.get("relevant_docs") or state.get("retrieved_docs", [])

    if not docs:
        return {
            "answer": "I couldn't find relevant information to answer this question. "
                      "Please try rephrasing your query.",
            "status": "no_context",
        }

    # Build context from docs
    context_parts = []
    for i, doc in enumerate(docs, 1):
        context_parts.append(
            f"[Doc {i}] ({doc['entity_type']}) {doc['content'][:1000]}"
        )
    context = "\n\n".join(context_parts)

    generator = _get_pipeline_llm(temperature=0.1)

    prompt = _GENERATE_PROMPT.format(context=context, question=query)
    resp = generator.invoke([HumanMessage(content=prompt)])

    log_llm_call(logger, model="generator", prompt_preview=query[:80])
    logger.info("Answer generated")

    return {"answer": resp.content.strip(), "status": "answer_generated"}


# ============================================================================
# Node: Hallucination Check
# ============================================================================

_HALLUCINATION_PROMPT = """You are a fact-checker. Compare the answer against the source documents.
Determine if the answer is fully supported by the documents, or if it contains
claims not found in the sources (hallucination).

Source Documents:
{sources}

Answer to Check:
{answer}

Respond with ONLY a JSON object: {{"supported": true}} or {{"supported": false}}"""


def hallucination_check_node(state: RAGState) -> dict:
    """Check if the generated answer is grounded in the source documents."""
    answer = state.get("answer", "")
    docs = state.get("relevant_docs", [])

    if not docs or not answer:
        return {"is_hallucinated": False, "status": "done"}

    sources = "\n\n".join(
        f"[{doc['entity_type']}] {doc['content'][:800]}" for doc in docs
    )

    checker = _get_pipeline_llm(temperature=0.0)

    prompt = _HALLUCINATION_PROMPT.format(sources=sources, answer=answer)
    resp = checker.invoke([HumanMessage(content=prompt)])
    text = resp.content.strip()

    log_llm_call(logger, model="hallucination-check", prompt_preview=answer[:80])

    supported = '"supported": true' in text.lower() or '"supported":true' in text.lower()

    if supported:
        logger.info("✅ Hallucination check passed — answer is grounded")
        return {"is_hallucinated": False, "status": "done"}
    else:
        logger.warning("⚠️ Hallucination detected — answer may not be grounded")
        return {"is_hallucinated": True, "status": "hallucinated"}


# ============================================================================
# Routing Functions
# ============================================================================

def route_after_grading(state: RAGState) -> str:
    """After grading, decide: generate answer or rewrite query."""
    if state.get("relevant_docs"):
        return "generate"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        logger.warning(f"Max retries ({MAX_RETRIES}) reached — generating with best available")
        return "generate"
    return "rewrite"


def route_after_hallucination(state: RAGState) -> str:
    """After hallucination check, decide: done or retry."""
    if not state.get("is_hallucinated"):
        return "done"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        logger.warning("Hallucination detected but max retries reached")
        return "done"
    return "rewrite"


# ============================================================================
# Graph Builder
# ============================================================================

def create_rag_graph():
    """Build the self-reflective RAG pipeline graph."""
    logger.info("Building Agentic RAG pipeline graph...")

    workflow = StateGraph(RAGState)

    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade", grade_documents_node)
    workflow.add_node("rewrite", rewrite_query_node)
    workflow.add_node("generate", generate_answer_node)
    workflow.add_node("hallucination_check", hallucination_check_node)

    # Edges
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "grade")

    workflow.add_conditional_edges(
        "grade",
        route_after_grading,
        {"generate": "generate", "rewrite": "rewrite"},
    )
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", "hallucination_check")
    workflow.add_conditional_edges(
        "hallucination_check",
        route_after_hallucination,
        {"done": END, "rewrite": "rewrite"},
    )

    graph = workflow.compile()
    logger.info("✓ Agentic RAG pipeline compiled")
    return graph


# ============================================================================
# Public Interface
# ============================================================================

_rag_graph = None


def get_rag_graph():
    """Get the singleton RAG pipeline graph."""
    global _rag_graph
    if _rag_graph is None:
        _rag_graph = create_rag_graph()
    return _rag_graph


def rag_query(question: str) -> dict:
    """
    Run a question through the agentic RAG pipeline.

    Returns:
        dict with keys: answer, relevant_docs, retry_count, is_hallucinated, status
    """
    graph = get_rag_graph()

    initial_state: RAGState = {
        "original_query": question,
        "current_query": question,
        "retrieved_docs": [],
        "relevant_docs": [],
        "answer": "",
        "is_hallucinated": False,
        "retry_count": 0,
        "status": "start",
    }

    with PhaseLogger(logger, f"RAG Pipeline: {question[:60]}"):
        final_state = graph.invoke(initial_state)

    return {
        "answer": final_state.get("answer", ""),
        "relevant_docs": final_state.get("relevant_docs", []),
        "retry_count": final_state.get("retry_count", 0),
        "is_hallucinated": final_state.get("is_hallucinated", False),
        "status": final_state.get("status", "unknown"),
    }
