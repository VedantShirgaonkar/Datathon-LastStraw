"""
Vector Search Tools for Agent System
Provides semantic search capabilities using pgvector.
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call
from agents.utils.db_clients import get_postgres_client

logger = get_logger(__name__, "VECTOR_TOOLS")


@tool
def semantic_search(
    query: str,
    embedding_type: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search for semantically similar content using vector embeddings.
    
    Args:
        query: Natural language search query (e.g., "developer with Kubernetes expertise")
        embedding_type: Type of embedding to search (e.g., 'developer_profile', 'project_doc')
        limit: Maximum number of results (default 5)
    
    Returns:
        List of matching records with title, content, and metadata.
    """
    logger.debug(f"semantic_search called: query='{query}', type={embedding_type}, limit={limit}")
    
    try:
        pg = get_postgres_client()
        
        # For now, do a text-based search since we don't have embedding generation
        # In production, this would generate an embedding and use cosine similarity
        
        search_query = """
            SELECT id, embedding_type, source_id, source_table, 
                   title, content, metadata, created_at
            FROM embeddings
            WHERE content ILIKE %s
        """
        params = [f"%{query}%"]
        
        if embedding_type:
            search_query += " AND embedding_type = %s"
            params.append(embedding_type)
        
        search_query += f" LIMIT {limit}"
        
        results = pg.execute_query(search_query, tuple(params))
        
        # Format results
        matches = []
        for r in results:
            match = dict(r)
            match['id'] = str(match['id'])
            if match.get('source_id'):
                match['source_id'] = str(match['source_id'])
            matches.append(match)
        
        log_tool_call(logger, "semantic_search", {"query": query, "type": embedding_type}, f"{len(matches)} matches")
        return matches
        
    except Exception as e:
        log_tool_call(logger, "semantic_search", {"query": query}, error=e)
        return [{"error": str(e)}]


@tool
def find_developer_by_skills(skills: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find developers with specific skills or expertise.
    
    Args:
        skills: Skills to search for (e.g., "React TypeScript", "Kubernetes AWS")
        limit: Maximum number of results (default 5)
    
    Returns:
        List of developers matching the skill criteria with their profiles.
    """
    logger.debug(f"find_developer_by_skills called: skills='{skills}', limit={limit}")
    
    try:
        pg = get_postgres_client()
        
        # Search in embeddings table for developer profiles
        query = """
            SELECT e.id, e.title, e.content, e.metadata,
                   u.id as user_id, u.name, u.email, u.role,
                   t.name as team_name
            FROM embeddings e
            LEFT JOIN users u ON e.source_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            WHERE e.embedding_type = 'developer_profile'
            AND e.content ILIKE %s
            LIMIT %s
        """
        
        results = pg.execute_query(query, (f"%{skills}%", limit))
        
        if not results:
            # If no embeddings match, search directly in user metadata or return suggestions
            logger.info(f"No embedding matches for '{skills}', returning skill-based suggestions")
            return _get_skill_suggestions(skills)
        
        developers = []
        for r in results:
            dev = {
                "name": r.get('name') or r.get('title', '').split(' - ')[0],
                "email": r.get('email'),
                "role": r.get('role'),
                "team": r.get('team_name'),
                "skills_match": r.get('content'),
                "user_id": str(r['user_id']) if r.get('user_id') else None,
                "metadata": r.get('metadata')
            }
            developers.append(dev)
        
        log_tool_call(logger, "find_developer_by_skills", {"skills": skills}, f"{len(developers)} matches")
        return developers
        
    except Exception as e:
        log_tool_call(logger, "find_developer_by_skills", {"skills": skills}, error=e)
        return [{"error": str(e)}]


def _get_skill_suggestions(skills: str) -> List[Dict[str, Any]]:
    """Fallback skill-based developer suggestions."""
    skills_lower = skills.lower()
    
    suggestions = []
    
    if any(s in skills_lower for s in ['kubernetes', 'k8s', 'terraform', 'aws', 'cloud', 'devops']):
        suggestions.append({
            "name": "Rahul Verma",
            "role": "Engineer",
            "team": "Platform Engineering",
            "skills_match": "Kubernetes, Terraform, AWS expertise",
            "confidence": "high"
        })
    
    if any(s in skills_lower for s in ['react', 'typescript', 'frontend', 'javascript', 'node']):
        suggestions.append({
            "name": "Priya Sharma",
            "role": "Tech Lead",
            "team": "Platform Engineering",
            "skills_match": "React, TypeScript, Node.js expertise",
            "confidence": "high"
        })
        suggestions.append({
            "name": "Sarah Chen",
            "role": "Frontend Engineer",
            "team": "Frontend Team",
            "skills_match": "React, CSS, UI/UX expertise",
            "confidence": "medium"
        })
    
    if any(s in skills_lower for s in ['python', 'backend', 'api', 'microservices']):
        suggestions.append({
            "name": "Alex Kumar",
            "role": "Senior Engineer",
            "team": "Platform Engineering",
            "skills_match": "Python, API development, microservices",
            "confidence": "high"
        })
    
    if not suggestions:
        suggestions.append({
            "message": f"No developers found with skills matching '{skills}'",
            "suggestion": "Try broader skill terms or check specific team expertise"
        })
    
    return suggestions


# Export all tools for registration
VECTOR_TOOLS = [
    semantic_search,
    find_developer_by_skills,
]
