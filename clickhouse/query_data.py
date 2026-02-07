"""
Quick script to query and display ClickHouse data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clickhouse_client import ClickHouseClient


def main():
    client = ClickHouseClient()
    
    print("\n" + "=" * 70)
    print("📊 CLICKHOUSE DATA OVERVIEW")
    print("=" * 70)
    
    # Total events
    count = client.get_event_count()
    print(f"\n📈 Total Events: {count:,}")
    
    # Events by source
    print("\n📦 Events by Source:")
    by_source = client.query("""
        SELECT source, count() as cnt
        FROM events
        GROUP BY source
        ORDER BY cnt DESC
    """)
    for row in by_source:
        print(f"   {row['source']:15} → {row['cnt']:,} events")
    
    # Events by type
    print("\n🔖 Top Event Types:")
    by_type = client.query("""
        SELECT event_type, count() as cnt
        FROM events
        GROUP BY event_type
        ORDER BY cnt DESC
        LIMIT 10
    """)
    for row in by_type:
        print(f"   {row['event_type']:20} → {row['cnt']:,} events")
    
    # Developer activity
    print("\n👥 Developer Activity (Last 30 Days):")
    dev_activity = client.query("""
        SELECT 
            actor_id,
            countIf(event_type = 'commit') as commits,
            countIf(event_type = 'pr_merged') as prs,
            countIf(event_type = 'pr_reviewed') as reviews
        FROM events
        WHERE timestamp >= now() - INTERVAL 30 DAY
        GROUP BY actor_id
        ORDER BY commits DESC
    """)
    for row in dev_activity:
        print(f"   {row['actor_id']:25} → Commits: {row['commits']:3} | PRs: {row['prs']:3} | Reviews: {row['reviews']:3}")
    
    # Project activity
    print("\n📁 Project Activity:")
    project_activity = client.query("""
        SELECT 
            project_id,
            count() as total_events,
            countIf(event_type = 'commit') as commits
        FROM events
        GROUP BY project_id
        ORDER BY total_events DESC
    """)
    for row in project_activity:
        print(f"   {row['project_id']:25} → {row['total_events']:3} events ({row['commits']} commits)")
    
    # DORA metrics
    print("\n📊 DORA Metrics (Last 7 Days):")
    dora = client.query("""
        SELECT 
            date,
            sum(deployments) as deployments,
            avg(avg_lead_time_hours) as avg_lead_time,
            sum(prs_merged) as prs
        FROM dora_daily_metrics
        WHERE date >= today() - 7
        GROUP BY date
        ORDER BY date DESC
        LIMIT 7
    """)
    if dora:
        for row in dora:
            lead_time = f"{row['avg_lead_time']:.1f}h" if row['avg_lead_time'] else "N/A"
            print(f"   {row['date']} → Deploys: {row['deployments']:2} | Lead Time: {lead_time:8} | PRs: {row['prs']:2}")
    else:
        print("   No DORA metrics yet (needs deployment/PR events)")
    
    # Recent events
    print("\n🕐 Recent Events (Last 10):")
    recent = client.get_recent_events(limit=10)
    for event in recent:
        print(f"   {event['timestamp']} | {event['source']:8} | {event['event_type']:20} | {event['actor_id']}")
    
    print("\n" + "=" * 70)
    print("✅ Query complete!")
    print("=" * 70 + "\n")
    
    client.close()


if __name__ == "__main__":
    main()
