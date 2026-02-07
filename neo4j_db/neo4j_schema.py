"""
Neo4j schema definition for Engineering Intelligence Platform.

Node Types:
- Developer: Individual developers/engineers
- Team: Engineering teams
- Project: Software projects/repositories
- Skill: Technical skills and technologies
- Sprint: Agile sprints
- Feature: Product features/epics

Relationship Types:
- WORKS_ON: Developer -> Project (with role, hours)
- MEMBER_OF: Developer -> Team
- OWNS: Team -> Project
- HAS_SKILL: Developer -> Skill (with proficiency level)
- DEPENDS_ON: Project -> Project
- CONTRIBUTES_TO: Developer -> Project (metrics)
- ASSIGNED_TO: Sprint -> Project
- BLOCKED_BY: Feature -> Feature
"""

from typing import List, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from neo4j_client import Neo4jClient


# Node constraints and indexes
CONSTRAINTS = [
    # Developer constraints
    "CREATE CONSTRAINT developer_email IF NOT EXISTS FOR (d:Developer) REQUIRE d.email IS UNIQUE",
    "CREATE CONSTRAINT developer_id IF NOT EXISTS FOR (d:Developer) REQUIRE d.id IS UNIQUE",
    
    # Team constraints
    "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT team_name IF NOT EXISTS FOR (t:Team) REQUIRE t.name IS UNIQUE",
    
    # Project constraints
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT project_key IF NOT EXISTS FOR (p:Project) REQUIRE p.key IS UNIQUE",
    
    # Skill constraints
    "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
    
    # Sprint constraints
    "CREATE CONSTRAINT sprint_id IF NOT EXISTS FOR (sp:Sprint) REQUIRE sp.id IS UNIQUE",
    
    # Feature constraints
    "CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (f:Feature) REQUIRE f.id IS UNIQUE",
]

INDEXES = [
    # Developer indexes
    "CREATE INDEX developer_name IF NOT EXISTS FOR (d:Developer) ON (d.name)",
    "CREATE INDEX developer_active IF NOT EXISTS FOR (d:Developer) ON (d.is_active)",
    
    # Project indexes
    "CREATE INDEX project_status IF NOT EXISTS FOR (p:Project) ON (p.status)",
    "CREATE INDEX project_priority IF NOT EXISTS FOR (p:Project) ON (p.priority)",
    
    # Skill indexes
    "CREATE INDEX skill_category IF NOT EXISTS FOR (s:Skill) ON (s.category)",
    
    # Sprint indexes
    "CREATE INDEX sprint_dates IF NOT EXISTS FOR (sp:Sprint) ON (sp.start_date, sp.end_date)",
    
    # Relationship indexes (for query performance)
    "CREATE INDEX works_on_role IF NOT EXISTS FOR ()-[r:WORKS_ON]-() ON (r.role)",
    "CREATE INDEX contributes_to_date IF NOT EXISTS FOR ()-[r:CONTRIBUTES_TO]-() ON (r.last_contribution_date)",
]


def create_constraints(client: Neo4jClient) -> List[str]:
    """
    Create all constraints in Neo4j database.
    
    Args:
        client: Neo4j client instance
    
    Returns:
        List of created constraint names
    """
    created = []
    
    for constraint in CONSTRAINTS:
        try:
            client.execute_write(constraint)
            # Extract constraint name from query
            constraint_name = constraint.split("CONSTRAINT")[1].split("IF NOT EXISTS")[0].strip()
            created.append(constraint_name)
            print(f"✓ Created constraint: {constraint_name}")
        except Exception as e:
            # Constraint might already exist
            print(f"⚠ Constraint already exists or error: {e}")
    
    return created


def create_indexes(client: Neo4jClient) -> List[str]:
    """
    Create all indexes in Neo4j database.
    
    Args:
        client: Neo4j client instance
    
    Returns:
        List of created index names
    """
    created = []
    
    for index in INDEXES:
        try:
            client.execute_write(index)
            # Extract index name from query
            index_name = index.split("INDEX")[1].split("IF NOT EXISTS")[0].strip()
            created.append(index_name)
            print(f"✓ Created index: {index_name}")
        except Exception as e:
            # Index might already exist
            print(f"⚠ Index already exists or error: {e}")
    
    return created


def setup_schema(client: Neo4jClient, verbose: bool = True) -> Dict[str, Any]:
    """
    Set up complete Neo4j schema with constraints and indexes.
    
    Args:
        client: Neo4j client instance
        verbose: Print progress messages
    
    Returns:
        Dictionary with setup results
    """
    if verbose:
        print("\n🚀 Setting up Neo4j schema...")
        print("=" * 60)
    
    # Create constraints first (they also create indexes)
    if verbose:
        print("\n📋 Creating constraints...")
    constraints = create_constraints(client)
    
    # Create additional indexes
    if verbose:
        print("\n📊 Creating indexes...")
    indexes = create_indexes(client)
    
    # Verify setup
    if verbose:
        print("\n✅ Schema setup complete!")
        print(f"   - Constraints created: {len(constraints)}")
        print(f"   - Indexes created: {len(indexes)}")
    
    return {
        "success": True,
        "constraints": constraints,
        "indexes": indexes
    }


def get_schema_info(client: Neo4jClient) -> Dict[str, Any]:
    """
    Get current schema information from database.
    
    Args:
        client: Neo4j client instance
    
    Returns:
        Dictionary with schema information
    """
    # Get constraints
    constraints_result = client.execute_query("SHOW CONSTRAINTS")
    constraints = [c["name"] for c in constraints_result]
    
    # Get indexes
    indexes_result = client.execute_query("SHOW INDEXES")
    indexes = [i["name"] for i in indexes_result]
    
    # Get node labels
    labels_result = client.execute_query("CALL db.labels()")
    labels = [l["label"] for l in labels_result]
    
    # Get relationship types
    rel_types_result = client.execute_query("CALL db.relationshipTypes()")
    rel_types = [r["relationshipType"] for r in rel_types_result]
    
    return {
        "constraints": constraints,
        "indexes": indexes,
        "node_labels": labels,
        "relationship_types": rel_types
    }


def verify_schema(client: Neo4jClient) -> Dict[str, bool]:
    """
    Verify that all required schema elements exist.
    
    Args:
        client: Neo4j client instance
    
    Returns:
        Dictionary with verification results
    """
    schema_info = get_schema_info(client)
    
    # Check if minimum constraints exist
    required_constraints = [
        "developer_email",
        "project_id",
        "team_id",
        "skill_name"
    ]
    
    constraints_ok = all(
        any(c.lower() in constraint.lower() for constraint in schema_info["constraints"])
        for c in required_constraints
    )
    
    # Check if indexes exist
    indexes_ok = len(schema_info["indexes"]) > 0
    
    return {
        "constraints_valid": constraints_ok,
        "indexes_exist": indexes_ok,
        "schema_ready": constraints_ok and indexes_ok
    }


if __name__ == "__main__":
    # Test schema setup
    client = Neo4jClient()
    
    try:
        # Setup schema
        result = setup_schema(client)
        
        print("\n" + "=" * 60)
        print("📊 Schema Information:")
        print("=" * 60)
        
        # Get and display schema info
        schema_info = get_schema_info(client)
        print(f"\nConstraints ({len(schema_info['constraints'])}):")
        for constraint in schema_info['constraints']:
            print(f"  - {constraint}")
        
        print(f"\nIndexes ({len(schema_info['indexes'])}):")
        for index in schema_info['indexes']:
            print(f"  - {index}")
        
        # Verify schema
        verification = verify_schema(client)
        print(f"\n✅ Schema verification: {'PASSED' if verification['schema_ready'] else 'FAILED'}")
        
    finally:
        client.close()
