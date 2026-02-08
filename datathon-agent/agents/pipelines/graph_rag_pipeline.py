"""
Graph RAG — Knowledge Graph-Powered Expert Discovery  (Feature 3.3)
=====================================================================

Combines **pgvector semantic similarity** with **Neo4j graph traversal**
to find the best expert for a given query, then has the LLM generate
a natural-language explanation of *why* each person was recommended.

Pipeline (6 nodes):
    START
      → vector_search          — pgvector cosine similarity on developer_profile embeddings
      → graph_search           — Neo4j CONTRIBUTED_TO / COLLABORATES_WITH / EXPERT_IN traversal
      → fuse_and_rank          — weighted score = 0.6 · semantic + 0.4 · graph
      → explain_recommendations — LLM-generated blurbs per candidate
      → synthesize             — LLM composes final ranked report
    → END

If Neo4j has no real graph data (common — Phase 0.5 was never executed),
the pipeline falls back to synthetic graph scores so the fusion step
and the full pipeline still function end-to-end.

Public API:
    find_expert(query: str, limit: int = 5) → dict
"""

from __future__ import annotations

import json
import re
import uuid
from typing import TypedDict, List, Dict, Any, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START

from agents.utils.logger import get_logger, log_llm_call
from agents.utils.config import get_config
from agents.tools.embedding_tools import get_embedding, format_vector_for_pg
from agents.utils.db_clients import get_postgres_client, get_neo4j_client

logger = get_logger(__name__, "GRAPH_RAG")


# ============================================================================
# State
# ============================================================================

class GraphRAGState(TypedDict):
    """State that flows through the Graph RAG pipeline."""
    query: str                                  # Original user query
    limit: int                                  # Max results to return
    vector_results: list[dict]                  # [{dev_id, name, similarity, …}]
    graph_results: list[dict]                   # [{dev_id, name, graph_score, path}]
    fused_ranking: list[dict]                   # [{dev_id, name, combined, …}]
    explanations: list[dict]                    # [{dev_id, name, explanation}]
    report: str                                 # Final synthesized report
    status: str                                 # ok / error


# ============================================================================
# Helpers
# ============================================================================

_config_cache = None


def _get_config():
    global _config_cache
    if _config_cache is None:
        _config_cache = get_config()
    return _config_cache


def _get_llm(model_key: str = "model_primary", temperature: float = 0.3):
    cfg = _get_config()
    model = getattr(cfg.featherless, model_key)
    return ChatOpenAI(
        model=model,
        api_key=cfg.featherless.api_key,
        base_url=cfg.featherless.base_url,
        temperature=temperature,
    )


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_serialise(obj: Any) -> Any:
    """Convert non-JSON-safe types coming from DB drivers."""
    from decimal import Decimal
    from datetime import date, datetime

    if isinstance(obj, dict):
        return {k: _safe_serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialise(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "hex") and callable(getattr(obj, "hex", None)):
        return str(obj)
    return obj


# ============================================================================
# Node 1 — Vector Search  (pgvector cosine similarity)
# ============================================================================

def vector_search_node(state: GraphRAGState) -> dict:
    """Embed the query and find closest developer_profile embeddings."""
    query = state["query"]
    limit = state.get("limit", 5)
    logger.info("▶ Starting: vector_search")

    try:
        pg = get_postgres_client()
        query_vec = get_embedding(query)
        vec_literal = format_vector_for_pg(query_vec)

        sql = f"""
            SELECT emb.source_id  AS employee_id,
                   e.full_name,
                   e.title,
                   e.role,
                   t.name           AS team_name,
                   emb.content      AS profile_content,
                   1 - (emb.embedding <=> '{vec_literal}'::vector) AS similarity
            FROM embeddings emb
            JOIN employees  e ON emb.source_id = e.id
            LEFT JOIN teams t ON e.team_id     = t.id
            WHERE emb.embedding_type = 'developer_profile'
              AND e.active = true
            ORDER BY emb.embedding <=> '{vec_literal}'::vector
            LIMIT %s
        """
        rows = pg.execute_query(sql, (limit * 2,))  # grab extra so fusion has room

        results = []
        for r in rows:
            d = _safe_serialise(dict(r))
            d["similarity"] = round(_safe_float(d.get("similarity")), 4)
            results.append(d)

        logger.info(f"✓ vector_search: {len(results)} matches (top sim={results[0]['similarity'] if results else 'N/A'})")
        return {"vector_results": results}

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"vector_results": [], "status": f"vector_search_error: {e}"}


# ============================================================================
# Node 2 — Graph Search  (Neo4j traversal)
# ============================================================================

# Canonical Neo4j schema we attempt to query
_NEO4J_QUERIES = {
    # 1. Direct topic expertise
    "expertise": """
        MATCH (d:Developer)-[r:EXPERT_IN]->(t:Topic)
        WHERE toLower(t.name) CONTAINS toLower($topic)
        RETURN d.name AS name, t.name AS topic,
               r.level AS level, r.contributions AS contributions,
               'EXPERT_IN' AS relationship
        ORDER BY r.contributions DESC
        LIMIT $limit
    """,
    # 2. Contribution to related services/repos
    "contribution": """
        MATCH (d:Developer)-[r:CONTRIBUTED_TO]->(p)
        WHERE toLower(p.name) CONTAINS toLower($topic)
        RETURN d.name AS name, p.name AS project,
               r.commits AS commits,
               'CONTRIBUTED_TO' AS relationship
        ORDER BY r.commits DESC
        LIMIT $limit
    """,
    # 3. Collaboration with developers who have expertise
    "collaboration": """
        MATCH (expert:Developer)-[:EXPERT_IN]->(t:Topic),
              (expert)-[r:COLLABORATES_WITH]-(d:Developer)
        WHERE toLower(t.name) CONTAINS toLower($topic)
        RETURN d.name AS name, expert.name AS expert_connection,
               t.name AS topic, r.strength AS strength,
               'COLLABORATES_WITH_EXPERT' AS relationship
        ORDER BY r.strength DESC
        LIMIT $limit
    """,
}


def _extract_topic_keywords(query: str) -> str:
    """
    Pull the most informative topic phrase from a natural-language query.
    e.g. "Who can help with payment processing timeout?" → "payment processing"
    """
    # Strip common question wrappers
    stripped = re.sub(
        r"(?i)^(who\s+(can|should|could|knows?|is\s+an?\s+expert\s+(in|on|at|with))\s+)"
        r"|^(find\s+me\s+(a|an|the)\s+)|^(help\s+me\s+with\s+)"
        r"|^(expert\s+(in|on|for)\s+)"
        r"|\?\s*$|\bhelp\b|\bwith\b|\babout\b|\bfor\b",
        "",
        query,
    ).strip()
    # Keep only meaningful words
    words = [w for w in stripped.split() if len(w) > 2]
    return " ".join(words[:4]) if words else query[:40]


def _synthetic_graph_results(query: str, limit: int) -> list[dict]:
    """
    When Neo4j has no real Developer/Topic nodes, generate plausible
    graph scores from the *synthetic helper functions* in neo4j_tools.
    This keeps the full pipeline functional for demo purposes.
    """
    from agents.tools.neo4j_tools import _get_synthetic_experts, _get_synthetic_collaborators

    topic = _extract_topic_keywords(query)
    results: dict[str, dict] = {}   # name → best record

    # Expert matches
    for exp in _get_synthetic_experts(topic):
        name = exp.get("expert", "")
        if not name or name.startswith("No specific"):
            continue
        score = 0.9 if exp.get("expertise_level") == "senior" else 0.6
        results[name] = {
            "name": name,
            "graph_score": score,
            "path": f"EXPERT_IN({exp.get('topic', topic)})",
            "detail": exp,
        }

    # Collaboration proximity
    for name_key in ["priya", "alex", "rahul"]:
        for collab in _get_synthetic_collaborators(name_key):
            cname = collab.get("collaborator", "")
            if cname and cname not in results:
                results[cname] = {
                    "name": cname,
                    "graph_score": round(_safe_float(collab.get("strength", 0.5)) * 0.7, 4),
                    "path": f"COLLABORATES_WITH({name_key})",
                    "detail": collab,
                }

    ranked = sorted(results.values(), key=lambda r: r["graph_score"], reverse=True)
    return ranked[:limit]


def graph_search_node(state: GraphRAGState) -> dict:
    """Query Neo4j for expertise/collaboration graph, fall back to synthetic."""
    query = state["query"]
    limit = state.get("limit", 5)
    logger.info("▶ Starting: graph_search")

    topic = _extract_topic_keywords(query)
    logger.info(f"Graph search topic: '{topic}'")

    try:
        neo4j = get_neo4j_client()

        # Quick check: do we have Developer nodes at all?
        check = neo4j.execute_query("MATCH (n:Developer) RETURN count(n) AS c LIMIT 1")
        has_graph = check and check[0].get("c", 0) > 0

        if not has_graph:
            logger.info("No Developer nodes in Neo4j — using synthetic graph data")
            results = _synthetic_graph_results(query, limit * 2)
            logger.info(f"✓ graph_search: {len(results)} synthetic results")
            return {"graph_results": results}

        # Real graph queries ─────────────────────────────────
        all_results: dict[str, dict] = {}

        for qname, cypher in _NEO4J_QUERIES.items():
            try:
                rows = neo4j.execute_query(cypher, {"topic": topic, "limit": limit})
                for r in rows:
                    name = r.get("name", "")
                    if not name:
                        continue
                    # Normalise a graph score 0-1
                    if qname == "expertise":
                        score = 0.95 if r.get("level") == "senior" else 0.7
                    elif qname == "contribution":
                        commits = _safe_float(r.get("commits"), 1)
                        score = min(1.0, commits / 50)
                    else:
                        score = _safe_float(r.get("strength"), 0.5)

                    # Keep best score per person
                    if name not in all_results or score > all_results[name]["graph_score"]:
                        all_results[name] = {
                            "name": name,
                            "graph_score": round(score, 4),
                            "path": r.get("relationship", qname),
                            "detail": _safe_serialise(dict(r)),
                        }
            except Exception as qe:
                logger.debug(f"Graph query '{qname}' failed (ok): {qe}")

        results = sorted(all_results.values(), key=lambda r: r["graph_score"], reverse=True)[:limit * 2]

        if not results:
            logger.info("Real graph queries returned nothing — falling back to synthetic")
            results = _synthetic_graph_results(query, limit * 2)

        logger.info(f"✓ graph_search: {len(results)} results")
        return {"graph_results": results}

    except Exception as e:
        logger.warning(f"Neo4j connection failed, using synthetic: {e}")
        results = _synthetic_graph_results(query, limit * 2)
        return {"graph_results": results}


# ============================================================================
# Node 3 — Fuse & Rank  (weighted combination)
# ============================================================================

VECTOR_WEIGHT = 0.6
GRAPH_WEIGHT = 0.4


def fuse_and_rank_node(state: GraphRAGState) -> dict:
    """Combine vector similarity and graph relevance into a single ranked list."""
    limit = state.get("limit", 5)
    logger.info("▶ Starting: fuse_and_rank")

    vec_by_name: dict[str, dict] = {}
    for v in state.get("vector_results", []):
        name = v.get("full_name", "")
        if name:
            vec_by_name[name] = v

    graph_by_name: dict[str, dict] = {}
    for g in state.get("graph_results", []):
        name = g.get("name", "")
        if name:
            graph_by_name[name]= g

    # Union of all candidate names
    all_names = set(vec_by_name.keys()) | set(graph_by_name.keys())

    fused: list[dict] = []
    for name in all_names:
        vec_score = _safe_float(vec_by_name.get(name, {}).get("similarity"), 0.0)
        graph_score = _safe_float(graph_by_name.get(name, {}).get("graph_score"), 0.0)
        combined = round(VECTOR_WEIGHT * vec_score + GRAPH_WEIGHT * graph_score, 4)

        entry = {
            "name": name,
            "vector_score": round(vec_score, 4),
            "graph_score": round(graph_score, 4),
            "combined_score": combined,
            # Carry forward profile data from vector results if available
            "title": vec_by_name.get(name, {}).get("title", ""),
            "role": vec_by_name.get(name, {}).get("role", ""),
            "team": vec_by_name.get(name, {}).get("team_name", ""),
            "profile": vec_by_name.get(name, {}).get("profile_content", ""),
            "graph_path": graph_by_name.get(name, {}).get("path", ""),
        }
        fused.append(entry)

    fused.sort(key=lambda r: r["combined_score"], reverse=True)
    fused = fused[:limit]

    logger.info(f"✓ fuse_and_rank: {len(fused)} candidates (top={fused[0]['combined_score'] if fused else 'N/A'})")
    return {"fused_ranking": fused}


# ============================================================================
# Node 4 — Explain Recommendations  (LLM narration per candidate)
# ============================================================================

def explain_recommendations_node(state: GraphRAGState) -> dict:
    """Have the LLM write a short explanation for each recommended expert."""
    fused = state.get("fused_ranking", [])
    query = state["query"]

    if not fused:
        return {"explanations": [], "status": "no_candidates"}

    logger.info("▶ Starting: explain_recommendations")

    # Build a single prompt with all candidates for efficiency
    candidate_block = "\n".join(
        f"  {i+1}. **{c['name']}** — {c['title'] or 'Engineer'} ({c['team'] or 'N/A'})\n"
        f"     Vector similarity: {c['vector_score']} | Graph relevance: {c['graph_score']} | Combined: {c['combined_score']}\n"
        f"     Graph path: {c['graph_path'] or 'none'}\n"
        f"     Profile: {(c.get('profile') or 'N/A')[:200]}"
        for i, c in enumerate(fused)
    )

    prompt = f"""You are an engineering expert recommender.

The user asked: "{query}"

Here are the top candidate experts, ranked by a fusion of semantic similarity
(how well their profile matches the query) and graph relevance
(their Neo4j relationships — expertise, contributions, collaborations):

{candidate_block}

For EACH candidate write 2-3 sentences explaining **why** they are recommended
for this query. Reference their skills, graph connections, or profile content.

Return a JSON array (no markdown fences, no extra text):
[
  {{"name": "...", "explanation": "..."}},
  ...
]
"""

    try:
        llm = _get_llm("model_primary", temperature=0.3)
        log_llm_call(logger, model="model_primary", prompt_preview=f"explain {len(fused)} candidates")
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = resp.content.strip()

        # Parse JSON array
        explanations = _parse_json_array(text)

        if not explanations:
            # Fallback: generate basic explanations
            explanations = [
                {"name": c["name"], "explanation": f"Recommended based on combined score of {c['combined_score']}."}
                for c in fused
            ]

        # Merge explanations back into fused ranking
        expl_by_name = {e["name"]: e.get("explanation", "") for e in explanations}
        enriched = []
        for c in fused:
            c_copy = dict(c)
            c_copy["explanation"] = expl_by_name.get(c["name"], f"Score: {c['combined_score']}")
            enriched.append(c_copy)

        logger.info(f"✓ explain_recommendations: {len(enriched)} explanations")
        return {"explanations": enriched}

    except Exception as e:
        logger.error(f"Explanation generation failed: {e}")
        # Graceful fallback
        enriched = [
            {**c, "explanation": f"Recommended (combined score {c['combined_score']})"}
            for c in fused
        ]
        return {"explanations": enriched}


def _parse_json_array(text: str) -> list:
    """Robustly extract a JSON array from LLM output."""
    # Try direct parse
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find [...] block
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return []


# ============================================================================
# Node 5 — Synthesize Final Report  (LLM summary)
# ============================================================================

def synthesize_node(state: GraphRAGState) -> dict:
    """Compose the final expert discovery report."""
    explanations = state.get("explanations", [])
    query = state["query"]

    if not explanations:
        return {
            "report": f"No experts found for: {query}",
            "status": "no_results",
        }

    logger.info("▶ Starting: synthesize_report")

    candidate_section = "\n".join(
        f"{i+1}. **{e['name']}** (combined score: {e.get('combined_score', 'N/A')})\n"
        f"   {e.get('explanation', '')}"
        for i, e in enumerate(explanations)
    )

    prompt = f"""You are a senior engineering manager summarizing expert recommendations.

The user asked: "{query}"

Here are the ranked experts with explanations:

{candidate_section}

Write a concise **Expert Discovery Report** with:
1. A one-line executive summary
2. The ranked recommendations (include name, title, team, and the explanation)
3. A brief "How to proceed" section suggesting the user reach out to the top 1-2 candidates

Keep it professional and concise (under 500 words).
"""

    try:
        llm = _get_llm("model_primary", temperature=0.3)
        log_llm_call(logger, model="model_primary", prompt_preview="synthesize expert report")
        resp = llm.invoke([HumanMessage(content=prompt)])
        report = resp.content.strip()

        logger.info(f"✓ synthesize: report generated ({len(report)} chars)")
        return {"report": report, "status": "ok"}

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        # Fallback: just format the candidates
        lines = [f"# Expert Discovery: {query}\n"]
        for i, e in enumerate(explanations):
            lines.append(f"{i+1}. **{e['name']}** — {e.get('explanation', '')}")
        return {"report": "\n".join(lines), "status": "ok_fallback"}


# ============================================================================
# Graph Construction
# ============================================================================

_graph_instance = None


def get_graph_rag_graph():
    """Build and cache the Graph RAG LangGraph sub-graph."""
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance

    logger.info("Building Graph RAG sub-graph...")

    builder = StateGraph(GraphRAGState)

    builder.add_node("vector_search", vector_search_node)
    builder.add_node("graph_search", graph_search_node)
    builder.add_node("fuse_and_rank", fuse_and_rank_node)
    builder.add_node("explain_recommendations", explain_recommendations_node)
    builder.add_node("synthesize", synthesize_node)

    builder.add_edge(START, "vector_search")
    builder.add_edge("vector_search", "graph_search")
    builder.add_edge("graph_search", "fuse_and_rank")
    builder.add_edge("fuse_and_rank", "explain_recommendations")
    builder.add_edge("explain_recommendations", "synthesize")
    builder.add_edge("synthesize", END)

    _graph_instance = builder.compile()
    logger.info("✓ Graph RAG sub-graph compiled")
    return _graph_instance


# ============================================================================
# Public API
# ============================================================================

def find_expert(query: str, limit: int = 5) -> dict:
    """
    Run the full Graph RAG expert discovery pipeline.

    Args:
        query: Natural-language question, e.g. "Who can help with payment processing?"
        limit: Max experts to return (default 5)

    Returns:
        dict with keys: report, fused_ranking, status
    """
    logger.info(f"🔍 Graph RAG expert search: {query}")

    graph = get_graph_rag_graph()

    initial_state: GraphRAGState = {
        "query": query,
        "limit": limit,
        "vector_results": [],
        "graph_results": [],
        "fused_ranking": [],
        "explanations": [],
        "report": "",
        "status": "",
    }

    result = graph.invoke(initial_state)

    return {
        "report": result.get("report", ""),
        "fused_ranking": result.get("fused_ranking", []),
        "explanations": result.get("explanations", []),
        "status": result.get("status", "unknown"),
    }
