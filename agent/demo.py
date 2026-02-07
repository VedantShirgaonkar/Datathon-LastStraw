"""
Demo script showing agent workflow with sample events.
Run this to see the agent in action without Kafka.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime, timezone
from agent.schemas.tool_schemas import KafkaEvent, EventSource


def print_section(title: str):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def demo_github_commit():
    """Demo: GitHub commit event processing"""
    print_section("DEMO 1: GitHub Commit Event → ClickHouse")
    
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
                "message": "feat: Add OAuth2 authentication endpoints",
                "files_changed": 5,
                "lines_added": 250,
                "lines_deleted": 30
            }
        }
    )
    
    print("📨 Incoming Event:")
    print(json.dumps(event.model_dump(), indent=2, default=str))
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify event → github/commit_pushed")
    print("  2. Select tools → insert_commit_event")
    print("  3. Extract params → project_id, developer_email, commit data")
    print("  4. Execute tool → Insert into ClickHouse events table")
    print("  5. Generate response → Success summary")
    
    print("\n✅ Expected Result:")
    print("  - Event inserted into ClickHouse events table")
    print("  - Developer activity metrics updated")
    print("  - Available for DORA metrics calculation")


def demo_pr_merged_dora():
    """Demo: PR merged event for DORA metrics"""
    print_section("DEMO 2: PR Merged Event → DORA Metrics")
    
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
                    "email": "alice@company.com",
                    "name": "Alice Johnson"
                },
                "created_at": "2025-01-15T08:00:00Z",
                "merged_at": "2025-01-15T10:30:00Z",
                "review_time_hours": 2.5,
                "lines_changed": 350
            }
        }
    )
    
    print("📨 Incoming Event:")
    print(json.dumps(event.model_dump(), indent=2, default=str))
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify event → github/pull_request_merged")
    print("  2. Select tools → insert_pr_event")
    print("  3. Extract params → PR number, review_time_hours (for lead time)")
    print("  4. Execute tool → Insert into ClickHouse with DORA data")
    print("  5. Trigger → dora_daily_metrics materialized view update")
    
    print("\n✅ Expected Result:")
    print("  - PR event in ClickHouse events table")
    print("  - DORA metrics updated:")
    print("    • Deployment Frequency: +1 deployment")
    print("    • Lead Time: 2.5 hours (creation to merge)")
    print("    • Available for trend analysis")


def demo_multi_tool_developer():
    """Demo: New developer onboarding with multiple tools"""
    print_section("DEMO 3: New Developer → Multi-Tool Execution")
    
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
                {"name": "PostgreSQL", "proficiency": "intermediate"},
                {"name": "Docker", "proficiency": "advanced"}
            ],
            "projects": ["proj-api", "proj-auth"]
        }
    )
    
    print("📨 Incoming Event:")
    print(json.dumps(event.model_dump(), indent=2, default=str))
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify event → ai_agent/developer_onboarded")
    print("  2. Select tools → [create_developer_node, add_skill_relationship x4]")
    print("  3. Execute in sequence:")
    print("     a. create_developer_node → Neo4j Developer node")
    print("     b. add_skill_relationship(Python, expert) → Neo4j")
    print("     c. add_skill_relationship(FastAPI, advanced) → Neo4j")
    print("     d. add_skill_relationship(PostgreSQL, intermediate) → Neo4j")
    print("     e. add_skill_relationship(Docker, advanced) → Neo4j")
    
    print("\n✅ Expected Result:")
    print("  - Developer node created in Neo4j")
    print("  - 4 HAS_SKILL relationships created")
    print("  - Developer searchable by skill (find_available_developers)")
    print("  - Ready for task assignment recommendations")


def demo_jira_sprint_analytics():
    """Demo: Jira issue completion for sprint analytics"""
    print_section("DEMO 4: Jira Issue Completed → Sprint Analytics")
    
    event = KafkaEvent(
        source=EventSource.JIRA,
        event_type="issue_completed",
        timestamp=datetime.now(timezone.utc),
        payload={
            "project_id": "proj-api",
            "issue": {
                "key": "API-123",
                "summary": "Implement OAuth2 token refresh",
                "type": "Story",
                "assignee": {
                    "email": "alice@company.com",
                    "name": "Alice Johnson"
                },
                "status_from": "In Progress",
                "status_to": "Done",
                "story_points": 8,
                "sprint": {
                    "id": "sprint-42",
                    "name": "Sprint 42"
                }
            }
        }
    )
    
    print("📨 Incoming Event:")
    print(json.dumps(event.model_dump(), indent=2, default=str))
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify event → jira/issue_completed")
    print("  2. Select tools → insert_jira_event")
    print("  3. Extract params → issue_key, story_points, status transition")
    print("  4. Execute tool → Insert into ClickHouse")
    print("  5. Trigger → DORA metrics update (story_points_completed)")
    
    print("\n✅ Expected Result:")
    print("  - Jira event in ClickHouse events table")
    print("  - Story points counted in DORA metrics")
    print("  - Developer activity summary updated")
    print("  - Sprint velocity data available")


def demo_query_analytics():
    """Demo: Query tools for analytics"""
    print_section("DEMO 5: Analytics Query → Developer Activity + DORA")
    
    print("🔍 Query 1: Get Developer Activity Summary")
    print("\nInput:")
    print("  - developer_email: alice@company.com")
    print("  - days: 30")
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify as query request")
    print("  2. Select tool → get_developer_activity_summary")
    print("  3. Execute → Query ClickHouse events table")
    
    print("\n✅ Expected Output:")
    print(json.dumps({
        "success": True,
        "developer_email": "alice@company.com",
        "period_days": 30,
        "commits": 45,
        "prs_opened": 12,
        "prs_merged": 10,
        "reviews": 8,
        "issues_completed": 15
    }, indent=2))
    
    print("\n" + "-" * 80)
    
    print("\n🔍 Query 2: Get Project DORA Metrics")
    print("\nInput:")
    print("  - project_id: proj-api")
    print("  - days: 30")
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify as query request")
    print("  2. Select tool → get_project_dora_metrics")
    print("  3. Execute → Query ClickHouse dora_daily_metrics view")
    
    print("\n✅ Expected Output:")
    print(json.dumps({
        "success": True,
        "project_id": "proj-api",
        "period_days": 30,
        "deployment_frequency": 2.5,  # deployments per day
        "avg_lead_time_hours": 3.2,  # hours from PR creation to merge
        "prs_merged": 75,
        "story_points_completed": 120
    }, indent=2))


def demo_skill_based_assignment():
    """Demo: Find developers by skill"""
    print_section("DEMO 6: Smart Task Assignment → Find Available Developers")
    
    print("🔍 Query: Find Python developers with availability")
    print("\nInput:")
    print("  - skill: Python")
    print("  - min_availability: 0.3 (30% capacity)")
    
    print("\n🤖 Agent Processing:")
    print("  1. Classify as developer search")
    print("  2. Select tool → find_available_developers")
    print("  3. Execute → Query Neo4j graph")
    print("     - MATCH developers with HAS_SKILL → Python")
    print("     - Calculate availability from project count")
    print("     - Filter by min_availability threshold")
    print("     - Order by availability + proficiency")
    
    print("\n✅ Expected Output:")
    print(json.dumps({
        "success": True,
        "matches": [
            {
                "email": "charlie@company.com",
                "name": "Charlie Davis",
                "availability": 0.67,
                "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "current_projects": ["proj-api"]
            },
            {
                "email": "alice@company.com",
                "name": "Alice Johnson",
                "availability": 0.33,
                "skills": ["Python", "React", "Node.js"],
                "current_projects": ["proj-api", "proj-frontend"]
            }
        ],
        "total_found": 2
    }, indent=2))
    
    print("\n💡 Use Case:")
    print("  → Recommend Charlie for new Python task (67% available)")
    print("  → Alice has lower availability but more diverse skills")


def main():
    """Run all demos"""
    print("\n" + "=" * 80)
    print("  DATABASE AGENT - WORKFLOW DEMONSTRATIONS")
    print("=" * 80)
    print("\nThis demonstrates how the agent processes different event types.")
    print("Agent uses LangGraph workflow with Featherless AI for reasoning.")
    print("All tools use Pydantic validation for type safety.")
    
    demos = [
        ("GitHub Commit", demo_github_commit),
        ("PR Merged (DORA)", demo_pr_merged_dora),
        ("Multi-Tool Execution", demo_multi_tool_developer),
        ("Jira Sprint Analytics", demo_jira_sprint_analytics),
        ("Analytics Queries", demo_query_analytics),
        ("Skill-Based Assignment", demo_skill_based_assignment)
    ]
    
    print("\n" + "-" * 80)
    print("Available Demos:")
    for i, (name, _) in enumerate(demos, 1):
        print(f"  {i}. {name}")
    print(f"  {len(demos) + 1}. Run All Demos")
    print("  0. Exit")
    print("-" * 80)
    
    try:
        choice = input("\nSelect demo (0-{}): ".format(len(demos) + 1))
        choice = int(choice)
        
        if choice == 0:
            print("\nExiting...")
            return
        elif choice == len(demos) + 1:
            for name, demo_func in demos:
                demo_func()
                input("\nPress Enter to continue...")
        elif 1 <= choice <= len(demos):
            demos[choice - 1][1]()
        else:
            print("\n❌ Invalid choice")
    
    except ValueError:
        print("\n❌ Invalid input")
    except KeyboardInterrupt:
        print("\n\nExiting...")
    
    print("\n" + "=" * 80)
    print("  To run the actual agent with Kafka:")
    print("    python agent/kafka_consumer.py")
    print("  ")
    print("  To test with real database operations:")
    print("    python agent/test_agent.py")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
