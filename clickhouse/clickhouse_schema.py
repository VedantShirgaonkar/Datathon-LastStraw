"""
ClickHouse schema definition for Engineering Intelligence Platform.

Tables:
- events: Raw events from all sources (GitHub, Jira, Notion, Prometheus)

Materialized Views:
- dora_daily_metrics: Pre-computed DORA metrics per project per day
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clickhouse_client import ClickHouseClient


# Table definitions
EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    event_id UUID DEFAULT generateUUIDv4(),
    timestamp DateTime DEFAULT now(),
    
    -- Source identification
    source LowCardinality(String),
    event_type LowCardinality(String),
    
    -- Entity identification
    project_id String,
    actor_id String,
    entity_id String,
    entity_type LowCardinality(String),
    
    -- Metadata (source-specific, stored as JSON)
    metadata String,
    
    INDEX idx_project project_id TYPE bloom_filter GRANULARITY 1,
    INDEX idx_actor actor_id TYPE bloom_filter GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (source, event_type, timestamp)
SETTINGS index_granularity = 8192
"""

# Materialized view for DORA metrics
DORA_METRICS_VIEW = """
CREATE MATERIALIZED VIEW IF NOT EXISTS dora_daily_metrics
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (project_id, date)
AS SELECT
    toDate(timestamp) as date,
    project_id,
    
    -- Deployment frequency (from GitHub workflow_run events)
    countIf(
        event_type = 'deployment' OR 
        (event_type = 'workflow_run' AND JSONExtractString(metadata, 'conclusion') = 'success')
    ) as deployments,
    
    -- Lead time for changes (from GitHub/Jira)
    avgIf(
        JSONExtractFloat(metadata, 'lead_time_hours'), 
        event_type = 'pr_merged'
    ) as avg_lead_time_hours,
    
    -- Change volume metrics
    countIf(event_type = 'pr_merged') as prs_merged,
    countIf(event_type = 'commit') as commits,
    
    -- Jira metrics
    sumIf(
        JSONExtractInt(metadata, 'story_points'), 
        event_type = 'issue_completed'
    ) as story_points_completed,
    
    -- Deployment failure tracking
    countIf(
        event_type = 'workflow_run' AND 
        JSONExtractString(metadata, 'conclusion') = 'failure'
    ) as failed_deployments
    
FROM events
GROUP BY date, project_id
"""

# Sample data comments for reference
SAMPLE_DATA_REFERENCE = """
-- SAMPLE EVENT TYPES BY SOURCE:

-- GITHUB EVENTS:
-- event_type: 'commit', 'pr_opened', 'pr_merged', 'pr_reviewed', 'workflow_run', 'deployment'
-- metadata: {lines_added, lines_deleted, review_time_hours, build_status, conclusion}

-- JIRA EVENTS:
-- event_type: 'issue_created', 'issue_updated', 'issue_completed', 'sprint_started', 'sprint_closed'
-- metadata: {story_points, status_from, status_to, blocked_time_hours, lead_time_hours}

-- NOTION EVENTS:
-- event_type: 'page_created', 'page_updated', 'database_item_created'
-- metadata: {page_title, database_name, properties}

-- PROMETHEUS METRICS:
-- event_type: 'metric_sample'
-- metadata: {metric_name, value, labels}
"""


def setup_schema(drop_existing: bool = False):
    """
    Set up ClickHouse schema (tables and materialized views).
    
    Args:
        drop_existing: If True, drop existing tables before creating (for testing)
    """
    client = ClickHouseClient()
    
    print("\n🔧 Setting up ClickHouse schema...")
    print("=" * 60)
    
    try:
        # Drop existing tables if requested
        if drop_existing:
            print("\n⚠️  Dropping existing tables...")
            try:
                client.command("DROP VIEW IF EXISTS dora_daily_metrics")
                print("   ✓ Dropped dora_daily_metrics view")
            except Exception as e:
                print(f"   ⚠️  Could not drop view: {e}")
            
            try:
                client.command("DROP TABLE IF EXISTS events")
                print("   ✓ Dropped events table")
            except Exception as e:
                print(f"   ⚠️  Could not drop table: {e}")
        
        # Create events table
        print("\n📊 Creating events table...")
        client.command(EVENTS_TABLE)
        print("   ✓ Events table created")
        
        # Create DORA metrics materialized view
        print("\n📈 Creating dora_daily_metrics materialized view...")
        client.command(DORA_METRICS_VIEW)
        print("   ✓ DORA metrics view created")
        
        # Verify schema
        print("\n✅ Schema setup complete!")
        print("\n📋 Created objects:")
        
        # List tables
        tables = client.query("SHOW TABLES")
        print("\n   Tables:")
        for table in tables:
            print(f"      - {table['name']}")
        
        # Check events table structure
        columns = client.query("DESCRIBE TABLE events")
        print("\n   Events table columns:")
        for col in columns:
            print(f"      - {col['name']}: {col['type']}")
        
        print("\n" + "=" * 60)
        print("✨ ClickHouse is ready for time-series analytics!")
        print("\nNext steps:")
        print("  1. Test with: python clickhouse/clickhouse_connection_test.py")
        print("  2. Insert sample data to verify schema works")
        print("  3. Query DORA metrics view")
        
    except Exception as e:
        print(f"\n❌ Error setting up schema: {e}")
        raise
    finally:
        client.close()


def insert_sample_data():
    """Insert sample events for testing"""
    from datetime import datetime, timedelta
    import random
    
    client = ClickHouseClient()
    
    print("\n📝 Inserting sample data...")
    
    # Sample projects and developers
    projects = ['proj-api', 'proj-frontend', 'proj-data-pipeline']
    developers = ['alice@company.com', 'bob@company.com', 'charlie@company.com']
    
    events = []
    
    # Generate 100 sample events over last 30 days
    for i in range(100):
        days_ago = random.randint(0, 30)
        timestamp = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))
        
        event_types = [
            ('github', 'commit', {'lines_added': random.randint(10, 200), 'lines_deleted': random.randint(5, 50)}),
            ('github', 'pr_merged', {'lead_time_hours': random.uniform(2, 48)}),
            ('github', 'pr_reviewed', {'review_time_minutes': random.randint(10, 120)}),
            ('jira', 'issue_completed', {'story_points': random.randint(1, 8), 'lead_time_hours': random.uniform(24, 168)}),
            ('github', 'workflow_run', {'conclusion': random.choice(['success', 'success', 'success', 'failure'])})
        ]
        
        source, event_type, metadata = random.choice(event_types)
        
        events.append({
            'source': source,
            'event_type': event_type,
            'timestamp': timestamp,
            'project_id': random.choice(projects),
            'actor_id': random.choice(developers),
            'entity_id': f'entity_{i}',
            'entity_type': event_type,
            'metadata': metadata
        })
    
    # Batch insert
    client.insert_events_batch(events)
    
    print(f"   ✓ Inserted {len(events)} sample events")
    
    # Query to verify
    count = client.get_event_count()
    print(f"   ✓ Total events in database: {count}")
    
    # Show sample DORA metrics
    print("\n📈 Sample DORA metrics:")
    for project in projects:
        metrics = client.get_dora_metrics(project, days=30)
        if metrics:
            total_deployments = sum(m['deployments'] for m in metrics)
            total_prs = sum(m['prs_merged'] for m in metrics)
            print(f"   {project}:")
            print(f"      - Deployments: {total_deployments}")
            print(f"      - PRs merged: {total_prs}")
    
    client.close()
    print("\n✨ Sample data inserted successfully!")


if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    drop_first = '--drop' in sys.argv
    add_samples = '--samples' in sys.argv
    
    if drop_first:
        print("⚠️  WARNING: This will drop existing tables and data!")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)
    
    # Set up schema
    setup_schema(drop_existing=drop_first)
    
    # Optionally insert sample data
    if add_samples:
        insert_sample_data()
