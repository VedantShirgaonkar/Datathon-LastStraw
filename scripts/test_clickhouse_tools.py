"""Test all 3 ClickHouse tools against real data."""
import sys, json
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
from agents.tools.clickhouse_tools import query_events, get_deployment_metrics, get_developer_activity

print("=" * 60)
print("TEST 1: query_events(days_back=60, limit=5)")
print("=" * 60)
result = query_events.invoke({"days_back": 60, "limit": 5})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 2: query_events(event_type='pr_reviewed', days_back=60, limit=3)")
print("=" * 60)
result = query_events.invoke({"event_type": "pr_reviewed", "days_back": 60, "limit": 3})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 3: get_deployment_metrics(days_back=60)")
print("=" * 60)
result = get_deployment_metrics.invoke({"days_back": 60})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 4: get_deployment_metrics(project_id='proj-api', days_back=60)")
print("=" * 60)
result = get_deployment_metrics.invoke({"project_id": "proj-api", "days_back": 60})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 5: get_developer_activity(days_back=60)")
print("=" * 60)
result = get_developer_activity.invoke({"days_back": 60})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 6: get_developer_activity(actor_id='alice@company.com', days_back=60)")
print("=" * 60)
result = get_developer_activity.invoke({"actor_id": "alice@company.com", "days_back": 60})
print(json.dumps(result, indent=2, default=str))

print("\n✅ All ClickHouse tools tests completed!")
