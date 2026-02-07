"""
Quick Demo - Show current state of all systems

Run: python demo_quick.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import json


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def demo_postgresql():
    """Show PostgreSQL data"""
    print_section("POSTGRESQL - Structured Data")
    
    try:
        from postgres.postgres_client import PostgresClient
        client = PostgresClient()
        
        # Tables
        result = client.execute_query("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        print(f"Tables: {', '.join([r['table_name'] for r in result])}")
        
        # Employees
        result = client.execute_query("SELECT full_name, email, title FROM employees WHERE active = true LIMIT 5")
        print(f"\nEmployees ({len(result)} shown):")
        for r in result:
            print(f"  • {r['full_name']} ({r.get('title', 'N/A')}) - {r['email']}")
        
        # Projects
        result = client.execute_query("SELECT name, status, jira_project_key FROM projects LIMIT 5")
        print(f"\nProjects ({len(result)} shown):")
        for r in result:
            print(f"  • {r['name']} [{r['status']}] - Jira: {r.get('jira_project_key', 'N/A')}")
        
        # Tasks
        result = client.execute_query("""
            SELECT status_category, COUNT(*) as cnt 
            FROM tasks GROUP BY status_category
        """)
        if result:
            print(f"\nTasks by status:")
            for r in result:
                print(f"  • {r['status_category'] or 'unknown'}: {r['cnt']}")
        else:
            print("\nTasks: 0 (run analytics sync to populate)")
        
        client.close()
        print("\n✓ PostgreSQL connected")
        
    except Exception as e:
        print(f"✗ PostgreSQL Error: {e}")


def demo_clickhouse():
    """Show ClickHouse data"""
    print_section("CLICKHOUSE - Time-Series Events")
    
    try:
        from clickhouse.clickhouse_client import ClickHouseClient
        client = ClickHouseClient()
        
        # Total events
        result = client.query("SELECT count() as cnt FROM events")
        print(f"Total events: {result[0]['cnt']}")
        
        # By source
        result = client.query("""
            SELECT source, count() as cnt 
            FROM events 
            GROUP BY source 
            ORDER BY cnt DESC
        """)
        print("\nEvents by source:")
        for r in result:
            print(f"  • {r['source']}: {r['cnt']}")
        
        # By event type
        result = client.query("""
            SELECT event_type, count() as cnt 
            FROM events 
            GROUP BY event_type 
            ORDER BY cnt DESC 
            LIMIT 10
        """)
        print("\nTop event types:")
        for r in result:
            print(f"  • {r['event_type']}: {r['cnt']}")
        
        # Recent events
        result = client.query("""
            SELECT timestamp, source, event_type, actor_id 
            FROM events 
            ORDER BY timestamp DESC 
            LIMIT 5
        """)
        print("\nRecent events:")
        for r in result:
            print(f"  • {r['timestamp']} | {r['source']}/{r['event_type']} by {r['actor_id']}")
        
        client.close()
        print("\n✓ ClickHouse connected")
        
    except Exception as e:
        print(f"✗ ClickHouse Error: {e}")


def demo_neo4j():
    """Show Neo4j data"""
    print_section("NEO4J - Collaboration Graph")
    
    try:
        from neo4j_db.neo4j_client import Neo4jClient
        client = Neo4jClient()
        
        # Get database stats
        stats = client.get_database_stats()
        print(f"Total nodes: {stats.get('total_nodes', 0)}")
        print(f"Total relationships: {stats.get('total_relationships', 0)}")
        
        if stats.get('node_counts'):
            print("\nNodes by type:")
            for label, count in stats['node_counts'].items():
                print(f"  • {label}: {count}")
        
        if stats.get('relationship_counts'):
            print("\nRelationships:")
            for rel_type, count in stats['relationship_counts'].items():
                print(f"  • {rel_type}: {count}")
        
        # Sample developers
        result = client.execute_query("MATCH (d:Developer) RETURN d.name as name, d.email as email LIMIT 5")
        if result:
            print("\nDevelopers (graph):")
            for r in result:
                print(f"  • {r['name']} - {r['email']}")
        
        client.close()
        print("\n✓ Neo4j connected")
        
    except Exception as e:
        print(f"✗ Neo4j Error: {e}")


def demo_embeddings():
    """Show pgvector embeddings data"""
    print_section("PGVECTOR - Embeddings (PostgreSQL)")
    
    try:
        from postgres.postgres_client import PostgresClient
        client = PostgresClient()
        
        # Total embeddings
        result = client.execute_query("SELECT COUNT(*) as cnt FROM embeddings")
        print(f"Total embeddings: {result[0]['cnt']}")
        
        # By type
        result = client.execute_query("""
            SELECT embedding_type, COUNT(*) as cnt 
            FROM embeddings 
            GROUP BY embedding_type
        """)
        if result:
            print("\nEmbeddings by type:")
            for r in result:
                print(f"  • {r['embedding_type']}: {r['cnt']}")
        
        # Check dimensions
        result = client.execute_query("""
            SELECT array_length(embedding::real[], 1) as dims
            FROM embeddings LIMIT 1
        """)
        if result and result[0].get('dims'):
            print(f"\nVector dimensions: {result[0]['dims']}")
        
        # Recent embeddings
        result = client.execute_query("""
            SELECT title, embedding_type, source_table, created_at
            FROM embeddings
            ORDER BY created_at DESC
            LIMIT 5
        """)
        if result:
            print("\nRecent embeddings:")
            for r in result:
                title = r['title'][:40] + '...' if r['title'] and len(r['title']) > 40 else r['title']
                print(f"  • {title} ({r['embedding_type']})")
        
        client.close()
        print("\n✓ pgvector connected (Pinecone API for generation, PostgreSQL for storage)")
        
    except Exception as e:
        print(f"✗ Embeddings Error: {e}")


def demo_agent_tools():
    """Show available agent tools"""
    print_section("AGENT TOOLS")
    
    try:
        from agent.tools.clickhouse_tools import clickhouse_tools
        from agent.tools.postgres_tools import postgres_tools
        from agent.tools.neo4j_tools import neo4j_tools
        from agent.tools.executor_tools import executor_tools
        from agent.tools.analytics_tools import analytics_tools
        
        print(f"ClickHouse tools: {len(clickhouse_tools)}")
        for t in clickhouse_tools:
            print(f"  • {t.name}")
        
        print(f"\nPostgreSQL tools: {len(postgres_tools)}")
        for t in postgres_tools[:5]:
            print(f"  • {t.name}")
        print(f"  ... and {len(postgres_tools)-5} more")
        
        print(f"\nNeo4j tools: {len(neo4j_tools)}")
        for t in neo4j_tools[:5]:
            print(f"  • {t.name}")
        
        print(f"\nExecutor tools: {len(executor_tools)}")
        for t in executor_tools[:5]:
            print(f"  • {t.name}")
        
        print(f"\nAnalytics tools: {len(analytics_tools)}")
        for t in analytics_tools:
            print(f"  • {t.name}")
        
        total = len(clickhouse_tools) + len(postgres_tools) + len(neo4j_tools) + len(executor_tools) + len(analytics_tools)
        print(f"\n✓ Total tools available: {total}")
        
    except Exception as e:
        print(f"✗ Tools Error: {e}")


def main():
    print("\n" + "="*60)
    print("  ENGINEERING INTELLIGENCE PLATFORM - QUICK DEMO")
    print("="*60)
    
    demo_postgresql()
    demo_clickhouse()
    demo_neo4j()
    demo_embeddings()
    demo_agent_tools()
    
    print_section("DEMO COMPLETE")
    print("""
Next steps:
  1. Run analytics sync: python agent/analytics_processor.py --sync all
  2. Run full demo: python demo_full_pipeline.py
  3. Test agent: python agent/test_agent.py
    """)


if __name__ == "__main__":
    main()
