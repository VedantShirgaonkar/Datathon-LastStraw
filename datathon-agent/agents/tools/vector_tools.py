"""
Vector Search Tools for Agent System
=====================================
Provides semantic search capabilities using pgvector cosine similarity.
Generates query embeddings locally via BAAI/bge-large-en-v1.5 (1024-dim)
and uses the pgvector <=> operator for nearest-neighbour search.

Tools:
    - semantic_search:  General-purpose vector similarity search across all embeddings.
    - find_developer_by_skills:  Skill-focused developer search combining vector
      similarity with structured employee data.
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call, log_db_query
from agents.utils.db_clients import get_postgres_client
from agents.tools.embedding_tools import get_embedding, format_vector_for_pg

logger = get_logger(__name__, "VECTOR_TOOLS")


def _serialise(row: Dict) -> Dict:
    """Convert non-JSON-safe types to primitives."""
    from decimal import Decimal
    from datetime import date, datetime

    out = {}
    for k, v in row.items():
        if hasattr(v, "hex") and callable(getattr(v, "hex", None)):
            out[k] = str(v)
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


@tool
def semantic_search(
    query: str,
    embedding_type: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search for semantically similar content using pgvector cosine similarity.

    This generates an embedding for the query text, then finds the closest
    vectors in the embeddings table using the <=> (cosine distance) operator.

    Args:
        query: Natural language search query
               (e.g. "developer with Kubernetes expertise",
                     "project about real-time data processing")
        embedding_type: Filter by type (e.g. 'developer_profile', 'project_doc').
                        If omitted, searches across all types.
        limit: Maximum number of results (default 5)

    Returns:
        List of matching records with title, content, metadata, and
        a similarity score (0-1, higher is better).
    """
    logger.debug(f"semantic_search: query='{query}', type={embedding_type}, limit={limit}")

    try:
        pg = get_postgres_client()

        # Generate query embedding
        query_vec = get_embedding(query)
        vec_literal = format_vector_for_pg(query_vec)

        # Build cosine similarity search
        # pgvector <=> gives cosine DISTANCE; similarity = 1 - distance
        search_query = f"""
            SELECT id, embedding_type, source_id, source_table,
                   title, content, metadata, created_at,
                   1 - (embedding <=> '{vec_literal}'::vector) AS similarity
            FROM embeddings
            WHERE 1=1
        """
        params: list = []

        if embedding_type:
            search_query += " AND embedding_type = %s"
            params.append(embedding_type)

        search_query += f" ORDER BY embedding <=> '{vec_literal}'::vector LIMIT %s"
        params.append(limit)

        log_db_query(logger, "pgvector", "cosine similarity search", {"type": embedding_type, "limit": limit})
        results = pg.execute_query(search_query, tuple(params))

        matches = []
        for r in results:
            match = _serialise(dict(r))
            # Round similarity for readability
            if "similarity" in match and match["similarity"] is not None:
                match["similarity"] = round(float(match["similarity"]), 4)
            matches.append(match)

        log_tool_call(
            logger, "semantic_search",
            {"query": query, "type": embedding_type},
            f"{len(matches)} matches (top sim={matches[0]['similarity'] if matches else 'N/A'})",
        )
        return matches

    except Exception as e:
        log_tool_call(logger, "semantic_search", {"query": query}, error=e)
        return [{"error": str(e)}]


@tool
def find_developer_by_skills(
    skills: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Find developers whose profiles best match the requested skills,
    using vector similarity search on developer_profile embeddings
    joined with the employees table for structured data.

    Args:
        skills: Skills/expertise to search for
                (e.g. "React TypeScript", "Kubernetes AWS DevOps",
                       "Python machine learning")
        limit: Maximum number of results (default 5)

    Returns:
        List of developers with full_name, email, title, team_name,
        matched profile content, and similarity score.
    """
    logger.debug(f"find_developer_by_skills: skills='{skills}', limit={limit}")

    try:
        pg = get_postgres_client()

        # Generate skill query embedding
        query_vec = get_embedding(skills)
        vec_literal = format_vector_for_pg(query_vec)

        # Join embeddings -> employees -> teams for rich results
        query = f"""
            SELECT emb.title AS profile_title,
                   emb.content AS profile_content,
                   emb.metadata,
                   1 - (emb.embedding <=> '{vec_literal}'::vector) AS similarity,
                   e.id AS employee_id, e.full_name, e.email,
                   e.title, e.role, e.hourly_rate, e.level,
                   t.name AS team_name
            FROM embeddings emb
            JOIN employees e ON emb.source_id = e.id
            LEFT JOIN teams t ON e.team_id = t.id
            WHERE emb.embedding_type = 'developer_profile'
              AND e.active = true
            ORDER BY emb.embedding <=> '{vec_literal}'::vector
            LIMIT %s
        """

        log_db_query(logger, "pgvector", "developer skill search", {"skills": skills, "limit": limit})
        results = pg.execute_query(query, (limit,))

        developers = []
        for r in results:
            dev = _serialise(dict(r))
            if "similarity" in dev and dev["similarity"] is not None:
                dev["similarity"] = round(float(dev["similarity"]), 4)
            developers.append(dev)

        log_tool_call(
            logger, "find_developer_by_skills",
            {"skills": skills},
            f"{len(developers)} matches",
        )
        return developers

    except Exception as e:
        log_tool_call(logger, "find_developer_by_skills", {"skills": skills}, error=e)
        return [{"error": str(e)}]


# Export all tools for registration
VECTOR_TOOLS = [
    semantic_search,
    find_developer_by_skills,
]
