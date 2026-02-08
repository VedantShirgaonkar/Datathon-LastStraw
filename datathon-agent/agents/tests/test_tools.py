"""
Test script for all agent tools.
Verifies each tool works correctly with the database.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.logger import get_logger, PhaseLogger
from agents.utils.config import load_config
from agents.utils.db_clients import close_all_connections

# Import tools
from agents.tools.postgres_tools import (
    get_developer, list_developers, get_project, 
    list_projects, get_team, get_developer_workload
)
from agents.tools.clickhouse_tools import (
    query_events, get_deployment_metrics, get_developer_activity
)
from agents.tools.vector_tools import (
    semantic_search, find_developer_by_skills
)
from agents.tools.neo4j_tools import (
    get_collaborators, get_team_collaboration_graph, find_knowledge_experts
)

logger = get_logger(__name__, "TOOL_TEST")


def test_postgres_tools():
    """Test PostgreSQL tools."""
    logger.info("Testing PostgreSQL tools...")
    
    # Test list_developers
    result = list_developers.invoke({"limit": 3})
    logger.info(f"list_developers: Found {len(result)} developers")
    assert len(result) > 0, "Should find at least one developer"
    
    # Test get_developer by name
    result = get_developer.invoke({"name": "Priya"})
    logger.info(f"get_developer(name=Priya): {result.get('name', 'Not found')}")
    assert result.get('name'), "Should find Priya"
    
    # Test get_team
    result = get_team.invoke({"name": "Platform"})
    logger.info(f"get_team(Platform): Found {result.get('member_count', 0)} members")
    assert result.get('members'), "Should find team members"
    
    # Test list_projects
    result = list_projects.invoke({"status": "active"})
    logger.info(f"list_projects(active): Found {len(result)} projects")
    
    # Test get_project
    result = get_project.invoke({"name": "API"})
    logger.info(f"get_project(API): {result.get('name', 'Not found')}")
    
    # Test get_developer_workload
    devs = list_developers.invoke({"limit": 1})
    if devs and devs[0].get('id'):
        result = get_developer_workload.invoke({"developer_id": devs[0]['id']})
        logger.info(f"get_developer_workload: {result.get('name')} - {result.get('total_allocation_percent', 0)}% allocated")
    
    logger.info("✓ PostgreSQL tools passed")


def test_clickhouse_tools():
    """Test ClickHouse tools."""
    logger.info("Testing ClickHouse tools...")
    
    # Test query_events
    result = query_events.invoke({"event_type": "commit", "days_back": 7})
    logger.info(f"query_events(commit): {len(result)} events")
    
    # Test get_deployment_metrics
    result = get_deployment_metrics.invoke({"project_name": "API Gateway"})
    logger.info(f"get_deployment_metrics: DORA rating = {result.get('dora_rating', 'N/A')}")
    
    # Test get_developer_activity
    result = get_developer_activity.invoke({"days_back": 7})
    logger.info(f"get_developer_activity: {len(result)} developers with activity")
    
    logger.info("✓ ClickHouse tools passed")


def test_vector_tools():
    """Test vector search tools."""
    logger.info("Testing vector search tools...")
    
    # Test semantic_search
    result = semantic_search.invoke({"query": "Kubernetes", "limit": 3})
    logger.info(f"semantic_search(Kubernetes): {len(result)} matches")
    
    # Test find_developer_by_skills
    result = find_developer_by_skills.invoke({"skills": "React TypeScript"})
    logger.info(f"find_developer_by_skills(React): {len(result)} matches")
    
    logger.info("✓ Vector tools passed")


def test_neo4j_tools():
    """Test Neo4j tools."""
    logger.info("Testing Neo4j tools...")
    
    # Test get_collaborators
    result = get_collaborators.invoke({"developer_name": "Priya Sharma"})
    logger.info(f"get_collaborators(Priya): {len(result)} collaborators")
    
    # Test get_team_collaboration_graph
    result = get_team_collaboration_graph.invoke({"team_name": "Platform Engineering"})
    logger.info(f"get_team_collaboration_graph: {len(result.get('nodes', []))} nodes, {len(result.get('edges', []))} edges")
    
    # Test find_knowledge_experts
    result = find_knowledge_experts.invoke({"topic": "API"})
    logger.info(f"find_knowledge_experts(API): {len(result)} experts")
    
    logger.info("✓ Neo4j tools passed")


def main():
    """Run all tool tests."""
    logger.info("=" * 60)
    logger.info("Starting Tool Tests")
    logger.info("=" * 60)
    
    try:
        # Load config
        load_config("/Users/rahul/Desktop/Datathon/.env")
        
        with PhaseLogger(logger, "PostgreSQL Tools"):
            test_postgres_tools()
        
        with PhaseLogger(logger, "ClickHouse Tools"):
            test_clickhouse_tools()
        
        with PhaseLogger(logger, "Vector Tools"):
            test_vector_tools()
        
        with PhaseLogger(logger, "Neo4j Tools"):
            test_neo4j_tools()
        
        logger.info("=" * 60)
        logger.info("✓ All tool tests passed!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"Tool test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_all_connections()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
