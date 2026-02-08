"""Test all 6 postgres tools against the live database."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
import json

# Test 1: get_developer by name
from agents.tools.postgres_tools import (
    get_developer, list_developers, get_project,
    list_projects, get_team, get_developer_workload,
)

print("=" * 60)
print("TEST 1: get_developer(name='Alex')")
print("=" * 60)
result = get_developer.invoke({"name": "Alex"})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 2: list_developers(limit=5)")
print("=" * 60)
result = list_developers.invoke({"limit": 5})
print(json.dumps(result, indent=2, default=str))

# Capture a developer ID for workload test
dev_id = result[0]["id"] if result and "id" in result[0] else None

print("\n" + "=" * 60)
print("TEST 3: list_developers(role='Lead', limit=5)")
print("=" * 60)
result = list_developers.invoke({"role": "Lead", "limit": 5})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 4: list_projects(limit=3)")
print("=" * 60)
result = list_projects.invoke({"limit": 3})
print(json.dumps(result, indent=2, default=str))

# Capture a project ID
proj_id = result[0]["id"] if result and "id" in result[0] else None

print("\n" + "=" * 60)
print(f"TEST 5: get_project(project_id='{proj_id}')")
print("=" * 60)
if proj_id:
    result = get_project.invoke({"project_id": proj_id})
    print(json.dumps(result, indent=2, default=str))
else:
    print("SKIP - no project_id found")

print("\n" + "=" * 60)
print("TEST 6: get_team(name='Backend')")
print("=" * 60)
result = get_team.invoke({"name": "Backend"})
if not result:
    # Try listing all teams
    from agents.utils.db_clients import get_postgres_client
    pg = get_postgres_client()
    teams = pg.execute_query("SELECT id, name FROM teams LIMIT 5")
    print(f"No 'Backend' team. Available teams: {[t['name'] for t in teams]}")
    if teams:
        result = get_team.invoke({"name": teams[0]["name"]})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print(f"TEST 7: get_developer_workload(developer_id='{dev_id}')")
print("=" * 60)
if dev_id:
    result = get_developer_workload.invoke({"developer_id": dev_id})
    print(json.dumps(result, indent=2, default=str))
else:
    print("SKIP - no dev_id found")

print("\n✅ All postgres_tools tests completed!")
