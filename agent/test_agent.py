"""
Test script for agent functionality.
Tests event processing, tool execution, and LangGraph workflow.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime, timezone
from agent.schemas.tool_schemas import KafkaEvent, EventSource
from agent.agent import DatabaseAgent


def test_commit_event():
    """Test GitHub commit event processing"""
    print("\n" + "=" * 80)
    print("TEST 1: GitHub Commit Event")
    print("=" * 80)
    
    event = KafkaEvent(
        source=EventSource.GITHUB,
        event_type="commit_pushed",
        timestamp=datetime.now(timezone.utc),
        payload={
            "repository": "proj-api",
            "project_id": "proj-api",
            "developer": {
                "email": "alice@company.com",
                "name": "Alice Johnson"
            },
            "commit": {
                "sha": "abc123def456",
                "message": "Add OAuth2 authentication",
                "files_changed": 3,
                "lines_added": 150,
                "lines_deleted": 20
            }
        }
    )
    
    print(f"\nEvent: {event.event_type} from {event.source}")
    print(f"Payload: {json.dumps(event.payload, indent=2)}")
    
    agent = DatabaseAgent()
    response = agent.process_event(event)
    
    print(f"\n{'✅ SUCCESS' if response.success else '❌ FAILED'}")
    print(f"Summary: {response.summary}")
    print(f"Actions taken: {len(response.actions_taken)}")
    for action in response.actions_taken:
        print(f"  - {action}")
    
    if response.errors:
        print(f"Errors: {response.errors}")
    
    return response.success


def test_pr_merged_event():
    """Test GitHub PR merged event"""
    print("\n" + "=" * 80)
    print("TEST 2: GitHub PR Merged Event")
    print("=" * 80)
    
    event = KafkaEvent(
        source=EventSource.GITHUB,
        event_type="pull_request_merged",
        timestamp=datetime.now(timezone.utc),
        payload={
            "repository": "proj-api",
            "project_id": "proj-api",
            "pull_request": {
                "number": 42,
                "title": "Implement user authentication",
                "author": {
                    "email": "bob@company.com",
                    "name": "Bob Smith"
                },
                "merged_by": {
                    "email": "alice@company.com"
                },
                "review_time_hours": 2.5,
                "lines_changed": 250
            }
        }
    )
    
    print(f"\nEvent: {event.event_type} from {event.source}")
    print(f"Payload: {json.dumps(event.payload, indent=2)}")
    
    agent = DatabaseAgent()
    response = agent.process_event(event)
    
    print(f"\n{'✅ SUCCESS' if response.success else '❌ FAILED'}")
    print(f"Summary: {response.summary}")
    print(f"Actions taken: {len(response.actions_taken)}")
    for action in response.actions_taken:
        print(f"  - {action}")
    
    if response.errors:
        print(f"Errors: {response.errors}")
    
    return response.success


def test_jira_issue_completed():
    """Test Jira issue completion event"""
    print("\n" + "=" * 80)
    print("TEST 3: Jira Issue Completed Event")
    print("=" * 80)
    
    event = KafkaEvent(
        source=EventSource.JIRA,
        event_type="issue_completed",
        timestamp=datetime.now(timezone.utc),
        payload={
            "project_id": "proj-api",
            "issue": {
                "key": "API-123",
                "summary": "Implement OAuth2 endpoints",
                "assignee": {
                    "email": "alice@company.com"
                },
                "status_from": "In Progress",
                "status_to": "Done",
                "story_points": 8
            }
        }
    )
    
    print(f"\nEvent: {event.event_type} from {event.source}")
    print(f"Payload: {json.dumps(event.payload, indent=2)}")
    
    agent = DatabaseAgent()
    response = agent.process_event(event)
    
    print(f"\n{'✅ SUCCESS' if response.success else '❌ FAILED'}")
    print(f"Summary: {response.summary}")
    print(f"Actions taken: {len(response.actions_taken)}")
    for action in response.actions_taken:
        print(f"  - {action}")
    
    if response.errors:
        print(f"Errors: {response.errors}")
    
    return response.success


def test_new_developer_event():
    """Test new developer onboarding event"""
    print("\n" + "=" * 80)
    print("TEST 4: New Developer Onboarding")
    print("=" * 80)
    
    event = KafkaEvent(
        source=EventSource.AI_AGENT,
        event_type="developer_onboarded",
        timestamp=datetime.now(timezone.utc),
        payload={
            "developer": {
                "email": "charlie@company.com",
                "name": "Charlie Davis",
                "team_id": "team-backend"
            },
            "skills": [
                {"name": "Python", "proficiency": "expert"},
                {"name": "FastAPI", "proficiency": "advanced"},
                {"name": "PostgreSQL", "proficiency": "intermediate"}
            ]
        }
    )
    
    print(f"\nEvent: {event.event_type} from {event.source}")
    print(f"Payload: {json.dumps(event.payload, indent=2)}")
    
    agent = DatabaseAgent()
    response = agent.process_event(event)
    
    print(f"\n{'✅ SUCCESS' if response.success else '❌ FAILED'}")
    print(f"Summary: {response.summary}")
    print(f"Actions taken: {len(response.actions_taken)}")
    for action in response.actions_taken:
        print(f"  - {action}")
    
    if response.errors:
        print(f"Errors: {response.errors}")
    
    return response.success


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("DATABASE AGENT - TEST SUITE")
    print("=" * 80)
    print("\nThis test suite validates:")
    print("  1. Event classification with Featherless AI")
    print("  2. Tool selection and parameter extraction")
    print("  3. Tool execution with Pydantic validation")
    print("  4. LangGraph workflow orchestration")
    
    try:
        # Run tests
        results = {
            "Commit Event": test_commit_event(),
            "PR Merged Event": test_pr_merged_event(),
            "Jira Issue Completed": test_jira_issue_completed(),
            "New Developer Onboarding": test_new_developer_event()
        }
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        for test_name, success in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"{test_name}: {status}")
        
        total_passed = sum(results.values())
        total_tests = len(results)
        
        print(f"\nTotal: {total_passed}/{total_tests} tests passed")
        
        if total_passed == total_tests:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️  {total_tests - total_passed} test(s) failed")
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
