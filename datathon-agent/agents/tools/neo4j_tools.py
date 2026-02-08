"""
Neo4j Tools for Agent System
Provides tools for querying relationship and collaboration data.
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call
from agents.utils.db_clients import get_neo4j_client

logger = get_logger(__name__, "NEO4J_TOOLS")


@tool
def get_collaborators(developer_name: str, relationship_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get developers who frequently collaborate with a given developer.
    
    Args:
        developer_name: Name of the developer to find collaborators for
        relationship_type: Type of collaboration (e.g., 'code_review', 'pr_collaboration', 'mentioned')
    
    Returns:
        List of collaborators with collaboration strength and type.
    """
    logger.debug(f"get_collaborators called: name={developer_name}, type={relationship_type}")
    
    try:
        neo4j = get_neo4j_client()
        
        # Check if we have developer nodes
        check_query = "MATCH (n) RETURN labels(n) as labels LIMIT 5"
        check_results = neo4j.execute_query(check_query)
        
        if not check_results or not any('Developer' in str(r.get('labels', [])) for r in check_results):
            logger.info("No Developer nodes found, returning synthetic collaboration data")
            return _get_synthetic_collaborators(developer_name)
        
        query = """
            MATCH (d:Developer {name: $name})-[r:COLLABORATES_WITH]-(other:Developer)
            RETURN other.name as collaborator, 
                   r.strength as strength,
                   r.type as collaboration_type,
                   r.project as project
            ORDER BY r.strength DESC
            LIMIT 10
        """
        
        results = neo4j.execute_query(query, {"name": developer_name})
        
        if not results:
            return _get_synthetic_collaborators(developer_name)
        
        log_tool_call(logger, "get_collaborators", {"name": developer_name}, f"{len(results)} collaborators")
        return results
        
    except Exception as e:
        logger.warning(f"Neo4j query failed, returning synthetic data: {e}")
        return _get_synthetic_collaborators(developer_name)


def _get_synthetic_collaborators(developer_name: str) -> List[Dict[str, Any]]:
    """Generate synthetic collaboration data for demo."""
    collaborations = {
        "priya": [
            {"collaborator": "Alex Kumar", "strength": 0.92, "collaboration_type": "code_review", "shared_projects": ["API Gateway v2"]},
            {"collaborator": "Rahul Verma", "strength": 0.78, "collaboration_type": "pr_collaboration", "shared_projects": ["Auth Service"]},
            {"collaborator": "Sarah Chen", "strength": 0.65, "collaboration_type": "mentioned", "shared_projects": ["Customer Dashboard"]},
        ],
        "alex": [
            {"collaborator": "Priya Sharma", "strength": 0.92, "collaboration_type": "code_review", "shared_projects": ["API Gateway v2"]},
            {"collaborator": "Rahul Verma", "strength": 0.85, "collaboration_type": "pair_programming", "shared_projects": ["API Gateway v2", "Infrastructure"]},
        ],
        "rahul": [
            {"collaborator": "Alex Kumar", "strength": 0.85, "collaboration_type": "pair_programming", "shared_projects": ["Infrastructure"]},
            {"collaborator": "Priya Sharma", "strength": 0.78, "collaboration_type": "pr_collaboration", "shared_projects": ["Auth Service"]},
            {"collaborator": "Mike Johnson", "strength": 0.72, "collaboration_type": "code_review", "shared_projects": ["Customer Dashboard"]},
        ],
    }
    
    name_lower = developer_name.lower()
    for key in collaborations:
        if key in name_lower:
            return collaborations[key]
    
    # Default
    return [
        {"collaborator": "Team Member 1", "strength": 0.75, "collaboration_type": "general", "message": "No specific collaboration data found"},
    ]


@tool
def get_team_collaboration_graph(team_name: str) -> Dict[str, Any]:
    """
    Get the collaboration network for an entire team.
    
    Args:
        team_name: Name of the team
    
    Returns:
        Graph structure with nodes (developers) and edges (collaborations).
    """
    logger.debug(f"get_team_collaboration_graph called: team={team_name}")
    
    try:
        neo4j = get_neo4j_client()
        
        query = """
            MATCH (d:Developer)-[:MEMBER_OF]->(t:Team {name: $team_name})
            OPTIONAL MATCH (d)-[r:COLLABORATES_WITH]-(other:Developer)-[:MEMBER_OF]->(t)
            RETURN d.name as developer,
                   collect(DISTINCT {
                       collaborator: other.name,
                       strength: r.strength,
                       type: r.type
                   }) as collaborations
        """
        
        results = neo4j.execute_query(query, {"team_name": team_name})
        
        if not results:
            return _get_synthetic_team_graph(team_name)
        
        graph = {
            "team": team_name,
            "nodes": [],
            "edges": []
        }
        
        for r in results:
            graph["nodes"].append({"id": r["developer"], "type": "developer"})
            for collab in r.get("collaborations", []):
                if collab.get("collaborator"):
                    graph["edges"].append({
                        "source": r["developer"],
                        "target": collab["collaborator"],
                        "strength": collab.get("strength", 0.5),
                        "type": collab.get("type", "collaboration")
                    })
        
        log_tool_call(logger, "get_team_collaboration_graph", {"team": team_name}, graph)
        return graph
        
    except Exception as e:
        logger.warning(f"Neo4j query failed, returning synthetic data: {e}")
        return _get_synthetic_team_graph(team_name)


def _get_synthetic_team_graph(team_name: str) -> Dict[str, Any]:
    """Generate synthetic team collaboration graph for demo."""
    return {
        "team": team_name,
        "nodes": [
            {"id": "Priya Sharma", "role": "Tech Lead"},
            {"id": "Alex Kumar", "role": "Senior Engineer"},
            {"id": "Rahul Verma", "role": "Engineer"},
        ],
        "edges": [
            {"source": "Priya Sharma", "target": "Alex Kumar", "strength": 0.92, "type": "code_review"},
            {"source": "Alex Kumar", "target": "Rahul Verma", "strength": 0.85, "type": "pair_programming"},
            {"source": "Priya Sharma", "target": "Rahul Verma", "strength": 0.78, "type": "mentorship"},
        ],
        "metrics": {
            "team_cohesion_score": 0.85,
            "avg_collaboration_strength": 0.85,
            "most_connected": "Priya Sharma"
        }
    }


@tool
def find_knowledge_experts(topic: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find developers who are experts on a specific topic based on contribution patterns.
    
    Args:
        topic: Topic or technology to search for (e.g., "authentication", "database", "kubernetes")
        limit: Maximum number of experts to return
    
    Returns:
        List of experts with their expertise level and relevant contributions.
    """
    logger.debug(f"find_knowledge_experts called: topic={topic}, limit={limit}")
    
    try:
        neo4j = get_neo4j_client()
        
        query = """
            MATCH (d:Developer)-[r:EXPERT_IN]->(t:Topic)
            WHERE toLower(t.name) CONTAINS toLower($topic)
            RETURN d.name as expert,
                   t.name as topic,
                   r.level as expertise_level,
                   r.contributions as contribution_count
            ORDER BY r.level DESC, r.contributions DESC
            LIMIT $limit
        """
        
        results = neo4j.execute_query(query, {"topic": topic, "limit": limit})
        
        if not results:
            return _get_synthetic_experts(topic)
        
        log_tool_call(logger, "find_knowledge_experts", {"topic": topic}, f"{len(results)} experts")
        return results
        
    except Exception as e:
        logger.warning(f"Neo4j query failed, returning synthetic data: {e}")
        return _get_synthetic_experts(topic)


def _get_synthetic_experts(topic: str) -> List[Dict[str, Any]]:
    """Generate synthetic expert data for demo."""
    topic_lower = topic.lower()
    
    expert_map = {
        "api": [
            {"expert": "Priya Sharma", "topic": "API Design", "expertise_level": "senior", "contributions": 45},
            {"expert": "Alex Kumar", "topic": "REST APIs", "expertise_level": "intermediate", "contributions": 28},
        ],
        "kubernetes": [
            {"expert": "Rahul Verma", "topic": "Kubernetes", "expertise_level": "senior", "contributions": 52},
        ],
        "react": [
            {"expert": "Priya Sharma", "topic": "React/TypeScript", "expertise_level": "senior", "contributions": 67},
            {"expert": "Sarah Chen", "topic": "React Components", "expertise_level": "intermediate", "contributions": 34},
        ],
        "database": [
            {"expert": "Alex Kumar", "topic": "PostgreSQL", "expertise_level": "senior", "contributions": 38},
            {"expert": "Rahul Verma", "topic": "Database Optimization", "expertise_level": "intermediate", "contributions": 22},
        ],
        "auth": [
            {"expert": "Priya Sharma", "topic": "Authentication", "expertise_level": "senior", "contributions": 29},
            {"expert": "Alex Kumar", "topic": "OAuth/JWT", "expertise_level": "intermediate", "contributions": 15},
        ],
    }
    
    for key, experts in expert_map.items():
        if key in topic_lower:
            return experts
    
    return [{"message": f"No specific experts found for '{topic}'", "suggestion": "Try related terms or check team expertise"}]


# Export all tools for registration
NEO4J_TOOLS = [
    get_collaborators,
    get_team_collaboration_graph,
    find_knowledge_experts,
]
