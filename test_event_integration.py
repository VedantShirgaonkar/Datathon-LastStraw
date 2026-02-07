"""
Test Event-to-Action Integration

Tests the full flow:
1. Receive event (simulated)
2. Event router suggests cross-platform actions
3. Agent selects tools (database + executor)
4. Execute tools

Run with: python test_event_integration.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from agent.event_router import get_suggested_actions, format_actions_for_prompt
from agent.schemas.tool_schemas import KafkaEvent, EventSource


# ==============================================================================
# TEST EVENTS
# ==============================================================================

# GitHub PR Merged Event - Should trigger: jira_transition_issue, notion_update_status
GITHUB_PR_MERGED = {
    "event_id": "gh-pr-001",
    "source": "github",
    "event_type": "pull_request",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "action": "closed",
        "number": 42,
        "pull_request": {
            "title": "[PROJ-123] Add user authentication feature",
            "body": "Implements login and registration",
            "merged": True,
            "user": {"login": "developer1"},
            "head": {"ref": "feature/auth"},
            "base": {"ref": "main"}
        },
        "repository": {
            "name": "backend-api",
            "full_name": "company/backend-api"
        }
    }
}

# GitHub Push Event with Jira Reference - Should trigger: jira_add_comment
GITHUB_PUSH = {
    "event_id": "gh-push-001",
    "source": "github",
    "event_type": "push",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "ref": "refs/heads/main",
        "commits": [
            {
                "id": "abc123def456",
                "message": "PROJ-456 Fix login validation bug",
                "author": {"name": "Developer", "email": "dev@company.com"}
            }
        ],
        "pusher": {"name": "developer1"},
        "repository": {"name": "backend-api", "full_name": "company/backend-api"}
    }
}

# GitHub Issue Opened with Bug Label - Should trigger: jira_create_issue
GITHUB_ISSUE_BUG = {
    "event_id": "gh-issue-001",
    "source": "github",
    "event_type": "issues",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "action": "opened",
        "issue": {
            "number": 99,
            "title": "Memory leak in session handler",
            "body": "Application memory increases over time",
            "user": {"login": "tester1"},
            "labels": [{"name": "bug"}, {"name": "critical"}]
        },
        "repository": {"name": "backend-api", "full_name": "company/backend-api"}
    }
}

# Jira Bug Created - Should trigger: github_create_issue, notion_create_page
JIRA_BUG_CREATED = {
    "event_id": "jira-001",
    "source": "jira",
    "event_type": "jira:issue_created",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "PROJ-789",
            "fields": {
                "summary": "API returns 500 on invalid input",
                "description": "When user sends malformed JSON, API crashes",
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "status": {"name": "To Do"}
            }
        }
    }
}

# Jira Status Change to Done - Should trigger: notion_update_status, github_close_issue
JIRA_STATUS_DONE = {
    "event_id": "jira-002",
    "source": "jira",
    "event_type": "jira:issue_updated",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "PROJ-123",
            "fields": {
                "summary": "Add user authentication",
                "status": {"name": "Done"}
            }
        },
        "changelog": {
            "items": [
                {"field": "status", "fromString": "In Progress", "toString": "Done"}
            ]
        }
    }
}

# Notion Page Created
NOTION_PAGE_CREATED = {
    "event_id": "notion-001",
    "source": "notion",
    "event_type": "page_created",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "raw": {
        "type": "page_created",
        "page": {"id": "page-abc123", "title": "Sprint 5 Planning"},
        "user": {"name": "PM"}
    }
}


# ==============================================================================
# TEST FUNCTIONS
# ==============================================================================

def test_event_router():
    """Test the event router to see suggested actions"""
    print("\n" + "="*80)
    print("TESTING EVENT ROUTER")
    print("="*80)
    
    test_events = [
        ("GitHub PR Merged", GITHUB_PR_MERGED),
        ("GitHub Push with Jira Ref", GITHUB_PUSH),
        ("GitHub Bug Issue Opened", GITHUB_ISSUE_BUG),
        ("Jira Bug Created", JIRA_BUG_CREATED),
        ("Jira Status → Done", JIRA_STATUS_DONE),
        ("Notion Page Created", NOTION_PAGE_CREATED),
    ]
    
    for name, event in test_events:
        print(f"\n{'─'*60}")
        print(f"📌 Event: {name}")
        print(f"   Source: {event['source']}, Type: {event['event_type']}")
        
        actions = get_suggested_actions(
            source=event['source'],
            event_type=event['event_type'],
            raw=event['raw']
        )
        
        if actions:
            print(f"   ✅ Suggested Actions ({len(actions)}):")
            for action in actions:
                priority = {1: "🔴 HIGH", 2: "🟡 MEDIUM", 3: "🟢 LOW"}.get(action.priority, "🟡")
                confirm = " ⚠️  (needs confirmation)" if action.requires_confirmation else ""
                print(f"      {priority} {action.action_type.value}{confirm}")
                print(f"         Reason: {action.reason[:60]}...")
        else:
            print(f"   ⚪ No cross-platform actions suggested")


def test_full_agent_flow():
    """Test the full agent flow with a sample event"""
    print("\n" + "="*80)
    print("TESTING FULL AGENT FLOW")
    print("="*80)
    
    try:
        from agent.agent import DatabaseAgent
        from agent.schemas.tool_schemas import KafkaEvent, EventSource
        
        # Create agent
        agent = DatabaseAgent()
        print("✅ Agent initialized")
        
        # Create test event
        test_event = KafkaEvent(
            event_id=GITHUB_PR_MERGED["event_id"],
            source=EventSource.GITHUB,
            event_type=GITHUB_PR_MERGED["event_type"],
            timestamp=datetime.now(timezone.utc),
            raw=GITHUB_PR_MERGED["raw"]
        )
        
        print(f"\n📤 Processing event: GitHub PR Merged")
        print(f"   PR Title: {test_event.raw['pull_request']['title']}")
        
        # Process through agent (this will call the LLM)
        response = agent.process_event(test_event)
        
        print(f"\n📥 Agent Response:")
        print(f"   Summary: {response.summary}")
        print(f"   Success: {'✅' if response.success else '❌'}")
        print(f"   Tools Executed: {response.tools_executed}")
        
        if response.actions_taken:
            print(f"   Actions:")
            for action in response.actions_taken:
                print(f"      - {action}")
        
        if response.errors:
            print(f"   Errors:")
            for error in response.errors:
                print(f"      ❌ {error}")
        
    except Exception as e:
        print(f"❌ Agent test failed: {e}")
        import traceback
        traceback.print_exc()


def test_executor_tools_directly():
    """Test executor tools directly (requires AWS credentials)"""
    print("\n" + "="*80)
    print("TESTING EXECUTOR TOOLS DIRECTLY")
    print("="*80)
    
    try:
        from agent.tools.executor_tools import executor_tools
        
        print(f"✅ Loaded {len(executor_tools)} executor tools:")
        for tool in executor_tools:
            print(f"   - {tool.name}: {tool.description[:50]}...")
        
        # Note: Actually invoking these would call AWS Lambda
        print("\n⚠️  Skipping actual execution (requires AWS Lambda deployment)")
        
    except Exception as e:
        print(f"❌ Executor tools test failed: {e}")


def simulate_kafka_event():
    """Simulate receiving a Kafka event and processing it"""
    print("\n" + "="*80)
    print("SIMULATING KAFKA EVENT FLOW")
    print("="*80)
    
    # This is what the Kafka consumer does
    raw_kafka_message = JIRA_STATUS_DONE
    
    print(f"\n📨 Received Kafka message:")
    print(f"   Topic: events.jira")
    print(f"   Event: {raw_kafka_message['event_type']}")
    
    # 1. Event Router Suggestions
    actions = get_suggested_actions(
        source=raw_kafka_message['source'],
        event_type=raw_kafka_message['event_type'],
        raw=raw_kafka_message['raw']
    )
    
    print(f"\n🔀 Event Router Analysis:")
    print(format_actions_for_prompt(actions))
    
    # 2. What the agent would do
    print(f"\n🤖 Agent would:")
    print("   1. Classify event as Jira status update")
    print("   2. Select tools:")
    print("      - insert_jira_event (ClickHouse) - record the event")
    print("      - notion_update_status - sync 'Done' to Notion")
    print("      - github_close_issue - close linked GitHub issue (if any)")
    print("   3. Execute selected tools")
    print("   4. Return summary of actions")


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Event Integration")
    parser.add_argument("--router", action="store_true", help="Test event router only")
    parser.add_argument("--agent", action="store_true", help="Test full agent flow (requires LLM)")
    parser.add_argument("--executor", action="store_true", help="Test executor tools")
    parser.add_argument("--simulate", action="store_true", help="Simulate Kafka event")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    args = parser.parse_args()
    
    if args.all or (not any([args.router, args.agent, args.executor, args.simulate])):
        # Default: run all safe tests (no LLM/AWS calls)
        test_event_router()
        test_executor_tools_directly()
        simulate_kafka_event()
    else:
        if args.router:
            test_event_router()
        if args.agent:
            test_full_agent_flow()
        if args.executor:
            test_executor_tools_directly()
        if args.simulate:
            simulate_kafka_event()
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
