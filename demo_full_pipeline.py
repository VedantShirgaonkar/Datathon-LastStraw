"""
Engineering Intelligence Platform - Demo Script

Demonstrates the full data flow:
1. Ingest raw events (GitHub, Jira) → ClickHouse
2. Generate embeddings → Pinecone
3. Analytics processor creates features → PostgreSQL
4. Query across all systems

Run: python demo_full_pipeline.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import json
import time
from datetime import datetime, timedelta
from uuid import uuid4

# Rich console for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, text): print(f"\n{'='*60}\n{text}\n{'='*60}")
    console = Console()


def print_header(text):
    if HAS_RICH:
        console.print(Panel(f"[bold cyan]{text}[/bold cyan]", expand=False))
    else:
        print(f"\n{'='*60}\n  {text}\n{'='*60}")


def print_step(step_num, text):
    if HAS_RICH:
        console.print(f"[bold green]Step {step_num}:[/bold green] {text}")
    else:
        print(f"\n>> Step {step_num}: {text}")


def print_success(text):
    if HAS_RICH:
        console.print(f"[green]✓[/green] {text}")
    else:
        print(f"  ✓ {text}")


def print_info(text):
    if HAS_RICH:
        console.print(f"[dim]{text}[/dim]")
    else:
        print(f"    {text}")


# =============================================================================
# SAMPLE EVENTS (Simulating Kafka messages)
# =============================================================================

SAMPLE_EVENTS = [
    # GitHub Push Event
    {
        "source": "github",
        "event_type": "push",
        "raw": {
            "ref": "refs/heads/main",
            "repository": {"full_name": "myorg/api-gateway", "id": 12345},
            "pusher": {"name": "john.doe", "email": "john.doe@company.com"},
            "commits": [
                {
                    "id": "abc123def456",
                    "message": "feat: Add rate limiting to API endpoints",
                    "author": {"name": "John Doe", "email": "john.doe@company.com"},
                    "timestamp": datetime.utcnow().isoformat()
                }
            ]
        }
    },
    # GitHub PR Merged
    {
        "source": "github",
        "event_type": "pull_request",
        "raw": {
            "action": "closed",
            "number": 42,
            "pull_request": {
                "title": "APIGW-123: Implement OAuth2 authentication",
                "body": "This PR adds OAuth2 support with JWT tokens for API authentication.",
                "user": {"login": "jane.smith"},
                "merged": True,
                "base": {"ref": "main"},
                "head": {"ref": "feature/APIGW-123-oauth"}
            }
        }
    },
    # GitHub Workflow Run (CI)
    {
        "source": "github",
        "event_type": "workflow_run",
        "raw": {
            "action": "completed",
            "workflow_run": {
                "conclusion": "success",
                "head_sha": "abc123def456",
                "name": "CI Pipeline"
            },
            "repository": {"full_name": "myorg/api-gateway"}
        }
    },
    # Jira Issue Created
    {
        "source": "jira",
        "event_type": "jira:issue_created",
        "raw": {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "key": "APIGW-124",
                "fields": {
                    "summary": "Implement caching layer for frequently accessed endpoints",
                    "description": "Add Redis caching to reduce database load on high-traffic endpoints",
                    "issuetype": {"name": "Story"},
                    "priority": {"name": "High"},
                    "status": {"name": "To Do"},
                    "assignee": {"emailAddress": "john.doe@company.com", "displayName": "John Doe"},
                    "reporter": {"emailAddress": "pm@company.com", "displayName": "Product Manager"},
                    "customfield_10004": 5  # Story points
                }
            }
        }
    },
    # Jira Issue Updated (Status Change)
    {
        "source": "jira",
        "event_type": "jira:issue_updated",
        "raw": {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "APIGW-123",
                "fields": {
                    "summary": "Implement OAuth2 authentication",
                    "status": {"name": "Done"},
                    "assignee": {"emailAddress": "jane.smith@company.com"}
                }
            },
            "changelog": {
                "items": [
                    {"field": "status", "fromString": "In Review", "toString": "Done"}
                ]
            }
        }
    }
]


# =============================================================================
# DEMO FUNCTIONS
# =============================================================================

def demo_clickhouse_ingest():
    """Demo: Ingest events into ClickHouse"""
    print_step(1, "Ingesting raw events into ClickHouse")
    
    try:
        from clickhouse.clickhouse_client import ClickHouseClient
        client = ClickHouseClient()
        
        events_to_insert = []
        for event in SAMPLE_EVENTS:
            events_to_insert.append({
                "source": event["source"],
                "event_type": event["event_type"],
                "timestamp": datetime.utcnow(),
                "project_id": "api-gateway",
                "actor_id": event["raw"].get("pusher", {}).get("email", 
                           event["raw"].get("issue", {}).get("fields", {}).get("assignee", {}).get("emailAddress", "unknown")),
                "entity_id": event["raw"].get("commits", [{}])[0].get("id", 
                            event["raw"].get("issue", {}).get("key", str(uuid4())[:8])),
                "entity_type": event["event_type"],
                "metadata": json.dumps(event["raw"])
            })
        
        # Insert events
        for e in events_to_insert:
            client.insert_event(e)
            print_success(f"Inserted {e['source']}/{e['event_type']}: {e['entity_id']}")
        
        # Query count
        result = client.query("SELECT count() as cnt FROM events")
        print_info(f"Total events in ClickHouse: {result[0]['cnt']}")
        
        client.close()
        return True
        
    except Exception as e:
        console.print(f"[red]ClickHouse Error: {e}[/red]")
        return False


def demo_embeddings():
    """Demo: Generate embeddings for RAG"""
    print_step(2, "Generating embeddings for semantic search")
    
    try:
        from agent.embedding_pipeline import process_event_for_embeddings
        from postgres.embedding_service import embed_text
        
        embedded_count = 0
        for event in SAMPLE_EVENTS[:2]:  # Just first 2 for demo
            items = process_event_for_embeddings(
                event["source"], 
                event["event_type"], 
                event["raw"]
            )
            if items:
                for item in items:
                    print_success(f"Embedded: {item['title'][:50]}...")
                    embedded_count += 1
        
        print_info(f"Created {embedded_count} embeddings for RAG search")
        return True
        
    except Exception as e:
        console.print(f"[yellow]Embedding skipped: {e}[/yellow]")
        return False


def demo_analytics_processor():
    """Demo: Run analytics processor to create PostgreSQL features"""
    print_step(3, "Running Analytics Processor (ClickHouse → PostgreSQL)")
    
    try:
        from agent.analytics_processor import AnalyticsProcessor
        
        processor = AnalyticsProcessor()
        
        # Sync tasks
        print_info("Syncing Jira issues to tasks table...")
        result = processor.sync_tasks_from_jira(since_hours=168)  # Last week
        print_success(f"Tasks: {result['tasks_created']} created, {result['tasks_updated']} updated")
        
        # Sync task events
        print_info("Syncing status transitions to task_events...")
        result = processor.sync_task_events(since_hours=168)
        print_success(f"Task events: {result['events_inserted']} inserted")
        
        # Sync CI pipelines
        print_info("Syncing CI pipelines...")
        result = processor.sync_ci_pipelines(since_hours=168)
        print_success(f"CI pipelines: {result['pipelines_created']} created")
        
        processor.close()
        return True
        
    except Exception as e:
        console.print(f"[red]Analytics Error: {e}[/red]")
        return False


def demo_query_postgres():
    """Demo: Query structured data from PostgreSQL"""
    print_step(4, "Querying structured features from PostgreSQL")
    
    try:
        from postgres.postgres_client import PostgresClient
        
        client = PostgresClient()
        
        # Employee count
        result = client.execute_query("SELECT COUNT(*) as cnt FROM employees")
        print_success(f"Employees: {result[0]['cnt']}")
        
        # Task summary
        result = client.execute_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status_category = 'done') as done,
                COUNT(*) FILTER (WHERE status_category = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE status_category = 'blocked') as blocked
            FROM tasks
        """)
        if result:
            r = result[0]
            print_success(f"Tasks: {r['total']} total, {r['done']} done, {r['in_progress']} in progress")
        
        # CI Pipeline summary
        result = client.execute_query("""
            SELECT status, COUNT(*) as cnt 
            FROM ci_pipelines 
            GROUP BY status
        """)
        if result:
            statuses = ", ".join([f"{r['status']}: {r['cnt']}" for r in result])
            print_success(f"CI Pipelines: {statuses}")
        
        # Recent activity
        result = client.execute_query("""
            SELECT e.full_name, COUNT(t.id) as tasks
            FROM employees e
            LEFT JOIN tasks t ON t.assignee_employee_id = e.id
            WHERE e.active = true
            GROUP BY e.id, e.full_name
            ORDER BY tasks DESC
            LIMIT 5
        """)
        if result:
            print_info("Top contributors by tasks:")
            for r in result:
                print_info(f"  • {r['full_name']}: {r['tasks']} tasks")
        
        client.close()
        return True
        
    except Exception as e:
        console.print(f"[red]PostgreSQL Error: {e}[/red]")
        return False


def demo_agent_query():
    """Demo: Ask the agent a question"""
    print_step(5, "Agent Query Demo")
    
    try:
        from agent.tools.analytics_tools import get_employee_performance_summary, get_project_health
        
        # Get employee performance
        print_info("Querying employee performance...")
        
        from postgres.postgres_client import PostgresClient
        client = PostgresClient()
        emp = client.execute_query("SELECT email FROM employees WHERE active = true LIMIT 1")
        client.close()
        
        if emp:
            result = get_employee_performance_summary(emp[0]['email'], months=3)
            if result.get('success'):
                print_success(f"Employee: {result['employee']['name']}")
                print_info(f"  Current workload: {result.get('current_workload', {})}")
        
        # Get project health
        print_info("Querying project health...")
        result = get_project_health("api-gateway")
        if result.get('success'):
            print_success(f"Project: {result['project']['name']}")
            ts = result.get('task_summary', {})
            print_info(f"  Tasks: {ts.get('total', 0)} total, {ts.get('done', 0)} done")
        
        return True
        
    except Exception as e:
        console.print(f"[yellow]Agent query skipped: {e}[/yellow]")
        return False


def demo_show_architecture():
    """Show the system architecture"""
    print_header("Engineering Intelligence Platform - Architecture")
    
    arch = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA FLOW ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   [Webhooks]              [MAIN AGENT]              [Actions]               │
│   GitHub ─────┐       ┌─────────────────┐       ┌──── Jira API              │
│   Jira ───────┼──────▶│   LangGraph     │──────▶├──── GitHub API            │
│   Notion ─────┘       │   + LLM         │       └──── Notion API            │
│                       └────────┬────────┘                                   │
│                                │                                            │
│              ┌─────────────────┼─────────────────┐                          │
│              │                 │                 │                          │
│              ▼                 ▼                 ▼                          │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                   │
│   │  ClickHouse  │   │   Pinecone   │   │    Neo4j     │                   │
│   │  (Raw Logs)  │   │ (Embeddings) │   │   (Graph)    │                   │
│   │              │   │              │   │              │                   │
│   │  Time-series │   │  Semantic    │   │  Collab      │                   │
│   │  Analytics   │   │  Search/RAG  │   │  Network     │                   │
│   └──────┬───────┘   └──────────────┘   └──────────────┘                   │
│          │                                                                  │
│          │  [ANALYTICS PROCESSOR]                                           │
│          │  Reads new events, creates features                              │
│          ▼                                                                  │
│   ┌─────────────────────────────────────────────────────┐                  │
│   │                   PostgreSQL                         │                  │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────┐  │                  │
│   │  │employees│ │  tasks  │ │ci_pipes │ │  metrics  │  │                  │
│   │  └─────────┘ └─────────┘ └─────────┘ └───────────┘  │                  │
│   └─────────────────────────────────────────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
    """
    print(arch)


def demo_show_tools():
    """Show available tools"""
    print_header("Available Agent Tools")
    
    tools_info = """
┌────────────────────────────────────────────────────────────────────────────┐
│  TOOL CATEGORY          │  TOOLS                                          │
├────────────────────────────────────────────────────────────────────────────┤
│  ClickHouse (Logs)      │  insert_github_commit, insert_jira_issue        │
│                         │  query_developer_activity, get_dora_metrics     │
├────────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL (Structured)│  create_employee, create_task, log_check_in     │
│                         │  get_employee_by_email, add_feedback            │
├────────────────────────────────────────────────────────────────────────────┤
│  Neo4j (Graph)          │  create_developer, link_collaboration           │
│                         │  find_experts, get_team_network                 │
├────────────────────────────────────────────────────────────────────────────┤
│  Executor (Actions)     │  create_jira_issue, create_github_pr            │
│                         │  update_notion_page, send_slack_message         │
├────────────────────────────────────────────────────────────────────────────┤
│  Analytics (Features)   │  sync_jira_tasks, compute_monthly_metrics       │
│                         │  get_employee_performance_summary               │
│                         │  get_project_health                             │
└────────────────────────────────────────────────────────────────────────────┘
    """
    print(tools_info)


# =============================================================================
# MAIN DEMO
# =============================================================================

def run_demo():
    """Run the full demo"""
    console.print("\n")
    print_header("Engineering Intelligence Platform - Full Demo")
    console.print("\n")
    
    # Show architecture
    demo_show_architecture()
    input("\nPress Enter to continue...")
    
    # Show tools
    demo_show_tools()
    input("\nPress Enter to start data flow demo...")
    
    console.print("\n")
    print_header("Live Data Flow Demo")
    console.print("\n")
    
    # Step 1: ClickHouse
    demo_clickhouse_ingest()
    console.print("")
    
    # Step 2: Embeddings
    demo_embeddings()
    console.print("")
    
    # Step 3: Analytics Processor
    demo_analytics_processor()
    console.print("")
    
    # Step 4: Query PostgreSQL
    demo_query_postgres()
    console.print("")
    
    # Step 5: Agent Query
    demo_agent_query()
    console.print("")
    
    print_header("Demo Complete!")
    console.print("""
[bold green]Summary:[/bold green]
  • Raw events stored in ClickHouse (time-series)
  • Embeddings generated for semantic search (Pinecone)
  • Analytics processor created structured features (PostgreSQL)
  • Agent can query across all systems
  
[bold cyan]Try these commands:[/bold cyan]
  • python agent/analytics_processor.py --sync all --hours 168
  • python -c "from agent.tools.analytics_tools import get_project_health; print(get_project_health('api-gateway'))"
    """ if HAS_RICH else """
Summary:
  - Raw events stored in ClickHouse (time-series)
  - Embeddings generated for semantic search (Pinecone)
  - Analytics processor created structured features (PostgreSQL)
  - Agent can query across all systems
    """)


if __name__ == "__main__":
    run_demo()
