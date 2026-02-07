# Low-Level System Architecture: Engineering Intelligence Platform

> **Technical Design Document for Team Distribution**
> 
> For: AI-Driven Enterprise Delivery & Workforce Intelligence

---

## Team Distribution Overview

| Team Member | Layer Ownership | Core Responsibilities |
|-------------|----------------|----------------------|
| **Member 1** | Data Ingestion Layer | Webhooks, API connectors, event normalization |
| **Member 2** | Database Layer | Schema design, data pipelines, query optimization |
| **Member 3** | AI/ML Layer | Agents, RAG system, embeddings, forecasting |
| **Member 4** | Presentation Layer | Dashboards, APIs, visualizations |

---

## 1. Data Ingestion Strategy: Build vs. Use APIs

### The Decision Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA INGESTION DECISION MATRIX                           │
├─────────────┬────────────────┬─────────────────┬───────────────────────────┤
│   Service   │  Build Custom? │ Use Their API?  │         Reasoning         │
├─────────────┼────────────────┼─────────────────┼───────────────────────────┤
│   GitHub    │      NO        │      YES        │ Excellent API, webhooks   │
│   Jira      │      NO        │      YES        │ Mature API + webhooks     │
│   Slack     │      NO        │      YES        │ Enterprise API required   │
│   Notion    │      NO        │      YES        │ Good API, rate limited    │
│ Prometheus  │    PARTIAL     │    PARTIAL      │ Self-hosted = direct      │
│   HRIS      │      YES       │    DEPENDS      │ Varies by vendor          │
└─────────────┴────────────────┴─────────────────┴───────────────────────────┘
```

### Detailed Breakdown Per Service

#### GitHub (Use API + Webhooks)

**Why NOT build custom:** GitHub's API is comprehensive, well-documented, and provides webhooks for real-time events. Building a custom scraper would be:
- Slower (no real-time)
- Rate-limited anyway
- Missing metadata (reactions, reviews, checks)

**What to use:**
```
REST API v3:  https://api.github.com
GraphQL v4:   https://api.github.com/graphql

Key Endpoints:
├── /repos/{owner}/{repo}/commits          # Commit history
├── /repos/{owner}/{repo}/pulls            # Pull requests
├── /repos/{owner}/{repo}/actions/runs     # CI/CD workflows
├── /repos/{owner}/{repo}/stats/contributors  # Contributor stats
└── /repos/{owner}/{repo}/events           # Activity feed
```

**Authentication:** GitHub App or Personal Access Token (PAT)
- GitHub App preferred for org-wide access
- Scopes needed: `repo`, `read:org`, `read:user`

---

#### Jira (Use API + Webhooks)

**Why NOT build custom:** Jira Cloud has robust REST APIs and webhook support. Self-hosted Jira Server also supports these.

**What to use:**
```
REST API v3:  https://{your-domain}.atlassian.net/rest/api/3
Agile API:    https://{your-domain}.atlassian.net/rest/agile/1.0

Key Endpoints:
├── /rest/api/3/search                     # JQL search (issues)
├── /rest/api/3/issue/{issueId}/changelog  # State transitions
├── /rest/agile/1.0/board/{boardId}/sprint # Sprint data
└── /rest/api/3/project/{key}/versions     # Releases
```

**Authentication:** OAuth 2.0 or API Token
- Create API token in Atlassian account settings

---

#### Slack (Use API - Enterprise Required for Analytics)

**Critical Limitation:** Full analytics require **Enterprise Grid** plan.

**What to use:**
```
Web API:  https://slack.com/api

Key Methods:
├── admin.analytics.getFile    # Enterprise analytics (daily JSON)
├── conversations.history      # Channel messages
├── users.info                 # User details
└── team.info                  # Workspace info
```

> [!WARNING]
> For hackathon demo, mock Slack data unless you have Enterprise Grid access.

---

#### Prometheus (Direct Access + PromQL)

**Build Custom:** YES, because Prometheus is typically self-hosted within your infrastructure.

**Connection Method:**
```
HTTP API:  http://{prometheus-server}:9090/api/v1

Key Endpoints:
├── /api/v1/query           # Instant query
├── /api/v1/query_range     # Range query
├── /api/v1/labels          # Label discovery
└── /api/v1/targets         # Scrape targets
```

**Example PromQL for engineering metrics:**
```promql
# Deployment success rate (last 24h)
sum(rate(deployments_total{status="success"}[24h])) / 
sum(rate(deployments_total[24h]))

# Average build duration
avg(build_duration_seconds)

# Error rate by service
sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
```

---

#### HRIS/HR Systems (Build Custom Connector)

**Build Custom:** YES, because each HRIS (Workday, BambooHR, SAP SuccessFactors) has different APIs.

**For hackathon:** Mock HRIS data with a simple JSON/CSV file:
```json
{
  "employees": [
    {
      "id": "EMP001",
      "name": "John Doe",
      "email": "john.doe@company.com",
      "github_username": "johndoe",
      "jira_username": "jdoe",
      "team": "Platform",
      "role": "Senior Engineer",
      "hourly_rate": 75.00,
      "start_date": "2022-03-15"
    }
  ]
}
```

---

## 2. Data Fetching Mechanisms: Webhooks vs Polling vs MCP

### When to Use What

```
┌────────────────────────────────────────────────────────────────────────────┐
│                     FETCHING MECHANISM DECISION TREE                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────┐                                                       │
│  │ Does the service│──YES──> ┌─────────────────┐                           │
│  │ support webhooks│         │ Is real-time    │──YES──> USE WEBHOOKS      │
│  └────────┬────────┘         │ critical?       │                           │
│           │                  └────────┬────────┘                           │
│          NO                          NO                                    │
│           │                           │                                    │
│           v                           v                                    │
│  ┌─────────────────┐         ┌─────────────────┐                           │
│  │ Does your AI    │──YES──> │ USE MCP         │                           │
│  │ need on-demand  │         │ (Model Context  │                           │
│  │ access?         │         │  Protocol)      │                           │
│  └────────┬────────┘         └─────────────────┘                           │
│           │                                                                │
│          NO                                                                │
│           │                                                                │
│           v                                                                │
│  ┌─────────────────┐                                                       │
│  │ USE POLLING     │                                                       │
│  │ (Scheduled)     │                                                       │
│  └─────────────────┘                                                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Per-Service Fetching Strategy

| Service | Primary | Secondary | Frequency | Events to Capture |
|---------|---------|-----------|-----------|-------------------|
| **GitHub** | Webhooks | Polling | Real-time + 15min | push, pull_request, workflow_run, issues |
| **Jira** | Webhooks | Polling | Real-time + 30min | issue_created, issue_updated, sprint_started/closed |
| **Slack** | Webhooks | N/A | Real-time | message, reaction_added, channel_created |
| **Prometheus** | Polling | N/A | 1-5 min | metrics scrape |
| **Notion** | Polling | N/A | 15 min | database queries |

### Webhook Implementation Details

#### Webhook Receiver Service

```python
# webhook_receiver/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import hashlib
import hmac
import json
from datetime import datetime

app = FastAPI()

# Event queue (use Redis/Kafka in production)
event_queue = []

@app.post("/webhooks/github")
async def github_webhook(request: Request):
    """Handle GitHub webhook events"""
    
    # 1. Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    
    expected_sig = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # 2. Parse event
    event_type = request.headers.get("X-GitHub-Event")
    payload = json.loads(body)
    
    # 3. Normalize and enqueue
    normalized_event = normalize_github_event(event_type, payload)
    event_queue.append(normalized_event)
    
    return JSONResponse({"status": "received"}, status_code=200)

@app.post("/webhooks/jira")
async def jira_webhook(request: Request):
    """Handle Jira webhook events"""
    
    body = await request.body()
    payload = json.loads(body)
    
    event_type = payload.get("webhookEvent")
    normalized_event = normalize_jira_event(event_type, payload)
    event_queue.append(normalized_event)
    
    return JSONResponse({"status": "received"}, status_code=200)
```

#### Normalized Event Schema

```python
# All events normalized to this structure
class NormalizedEvent:
    id: str                    # Unique event ID
    source: str                # "github" | "jira" | "slack" | "prometheus"
    event_type: str            # "commit" | "pr_merged" | "issue_updated" | ...
    timestamp: datetime        # When event occurred
    actor_id: str             # Who triggered (email/username)
    project_id: str           # Project/repo identifier
    entity_id: str            # Issue ID, PR number, commit SHA
    entity_type: str          # "commit" | "pull_request" | "issue" | ...
    metadata: dict            # Source-specific additional data
    raw_payload: dict         # Original payload for debugging
```

### MCP (Model Context Protocol) Implementation

**When to use MCP:** For AI-initiated, on-demand queries where the LLM needs fresh data.

```python
# mcp_servers/jira_server.py
from mcp.server import McpServer
from mcp.types import Tool, Resource

server = McpServer("jira-mcp-server")

@server.tool("get_sprint_progress")
async def get_sprint_progress(project_key: str, sprint_id: int):
    """Get current sprint progress for AI context"""
    
    sprint = await jira_client.get_sprint(project_key, sprint_id)
    issues = await jira_client.get_sprint_issues(sprint_id)
    
    return {
        "sprint_name": sprint.name,
        "start_date": sprint.start_date,
        "end_date": sprint.end_date,
        "total_issues": len(issues),
        "completed": sum(1 for i in issues if i.status == "Done"),
        "in_progress": sum(1 for i in issues if i.status == "In Progress"),
        "blocked": sum(1 for i in issues if i.status == "Blocked"),
        "story_points_completed": sum(i.story_points for i in issues if i.status == "Done"),
        "story_points_remaining": sum(i.story_points for i in issues if i.status != "Done"),
    }

@server.tool("get_developer_workload")
async def get_developer_workload(developer_email: str):
    """Get current workload for a developer"""
    
    issues = await jira_client.search_issues(f'assignee="{developer_email}" AND status != Done')
    
    return {
        "open_issues": len(issues),
        "total_story_points": sum(i.story_points or 0 for i in issues),
        "issues_by_priority": {
            "high": sum(1 for i in issues if i.priority == "High"),
            "medium": sum(1 for i in issues if i.priority == "Medium"),
            "low": sum(1 for i in issues if i.priority == "Low"),
        }
    }

@server.resource("jira://project/{key}/velocity")
async def get_velocity_history(key: str):
    """Historical velocity data as a resource"""
    sprints = await jira_client.get_completed_sprints(key, limit=10)
    return [{"sprint": s.name, "velocity": s.completed_points} for s in sprints]
```

### Polling Service Design

```python
# polling_service/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()

# GitHub: Poll for missed webhooks and historical sync
@scheduler.scheduled_job(IntervalTrigger(minutes=15))
async def poll_github_commits():
    """Catch up on any missed commits"""
    for repo in tracked_repos:
        commits = await github_client.get_commits(repo, since=last_sync_time)
        for commit in commits:
            normalized = normalize_github_event("push", commit)
            await event_processor.process(normalized)

# Prometheus: Regular metrics scrape
@scheduler.scheduled_job(IntervalTrigger(minutes=1))
async def poll_prometheus_metrics():
    """Scrape key metrics from Prometheus"""
    metrics = [
        "deployment_success_rate",
        "build_duration_seconds",
        "error_rate_5xx",
        "mttr_seconds"
    ]
    for metric in metrics:
        result = await prometheus_client.query(metric)
        await metrics_store.save(metric, result)

# Notion: Sync roadmap data
@scheduler.scheduled_job(IntervalTrigger(minutes=30))
async def poll_notion_roadmap():
    """Sync roadmap from Notion database"""
    pages = await notion_client.query_database(ROADMAP_DB_ID)
    for page in pages:
        await roadmap_store.upsert(page)
```

---

## 3. Database Architecture

### Multi-Database Strategy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATABASE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    Purpose: Entity storage, relationships,         │
│  │   PostgreSQL    │    user data, project metadata                     │
│  │   (Primary DB)  │    Tech: PostgreSQL 15+                            │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           │  ┌──────────────────────────────────────────────────────┐  │
│           ├──│ Tables: users, projects, teams, identity_mappings   │  │
│           │  └──────────────────────────────────────────────────────┘  │
│           │                                                             │
│  ┌────────┴────────┐    Purpose: Time-series metrics, events,           │
│  │   ClickHouse    │    high-volume aggregations                        │
│  │  (Time-Series)  │    Tech: ClickHouse or TimescaleDB                 │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           │  ┌──────────────────────────────────────────────────────┐  │
│           ├──│ Tables: events, metrics, dora_snapshots             │  │
│           │  └──────────────────────────────────────────────────────┘  │
│           │                                                             │
│  ┌────────┴────────┐    Purpose: Semantic search, developer             │
│  │   ChromaDB /    │    profiles, skill matching                        │
│  │   Pinecone      │    Tech: ChromaDB (local) or Pinecone (cloud)      │
│  │  (Vector DB)    │                                                    │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           │  ┌──────────────────────────────────────────────────────┐  │
│           ├──│ Collections: developer_profiles, project_docs       │  │
│           │  └──────────────────────────────────────────────────────┘  │
│           │                                                             │
│  ┌────────┴────────┐    Purpose: Relationship queries (optional)        │
│  │     Neo4j       │    Team → Project → Developer dependencies         │
│  │   (Graph DB)    │    Tech: Neo4j Community                           │
│  └─────────────────┘                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### PostgreSQL Schema (Primary)

```sql
-- Core entities
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50),  -- 'engineer', 'manager', 'hr', 'finance', 'executive'
    team_id UUID REFERENCES teams(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    manager_id UUID REFERENCES users(id),
    department VARCHAR(100)
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    jira_project_key VARCHAR(50),
    github_repo VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    priority VARCHAR(20) DEFAULT 'medium',
    start_date DATE,
    target_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Identity resolution (link users across systems)
CREATE TABLE identity_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    source VARCHAR(50) NOT NULL,  -- 'github', 'jira', 'slack'
    external_id VARCHAR(255) NOT NULL,
    external_username VARCHAR(255),
    verified BOOLEAN DEFAULT false,
    UNIQUE(source, external_id)
);

-- Developer cost data (from HRIS)
CREATE TABLE developer_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    hourly_rate DECIMAL(10, 2),
    effective_date DATE,
    UNIQUE(user_id, effective_date)
);
```

### ClickHouse Schema (Time-Series)

```sql
-- Raw events table (partitioned by day)
CREATE TABLE events (
    event_id UUID,
    source LowCardinality(String),  -- 'github', 'jira', 'slack'
    event_type LowCardinality(String),
    timestamp DateTime,
    actor_id String,
    project_id String,
    entity_id String,
    entity_type LowCardinality(String),
    metadata String,  -- JSON
    
    -- Partition and order for efficient queries
    INDEX idx_actor actor_id TYPE bloom_filter GRANULARITY 1,
    INDEX idx_project project_id TYPE bloom_filter GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (source, event_type, timestamp);

-- Pre-aggregated DORA metrics (materialized view)
CREATE MATERIALIZED VIEW dora_daily_metrics
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (project_id, date)
AS SELECT
    toDate(timestamp) as date,
    project_id,
    
    -- Deployment Frequency
    countIf(event_type = 'deployment') as deployment_count,
    
    -- Lead Time (avg seconds from commit to deploy)
    avgIf(
        JSONExtractFloat(metadata, 'lead_time_seconds'),
        event_type = 'deployment'
    ) as avg_lead_time_seconds,
    
    -- Change Failure Rate
    countIf(event_type = 'deployment' AND JSONExtractBool(metadata, 'is_failure')) as failed_deployments,
    
    -- PR Metrics
    countIf(event_type = 'pr_merged') as prs_merged,
    avgIf(
        JSONExtractFloat(metadata, 'review_time_hours'),
        event_type = 'pr_merged'
    ) as avg_review_time_hours

FROM events
GROUP BY date, project_id;

-- Developer activity metrics
CREATE MATERIALIZED VIEW developer_daily_activity
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (actor_id, date)
AS SELECT
    toDate(timestamp) as date,
    actor_id,
    
    countIf(event_type = 'commit') as commits,
    countIf(event_type = 'pr_opened') as prs_opened,
    countIf(event_type = 'pr_merged') as prs_merged,
    countIf(event_type = 'pr_reviewed') as reviews_given,
    countIf(event_type = 'issue_completed') as issues_completed,
    
    sumIf(
        JSONExtractInt(metadata, 'lines_added'),
        event_type = 'commit'
    ) as lines_added,
    sumIf(
        JSONExtractInt(metadata, 'lines_deleted'),
        event_type = 'commit'
    ) as lines_deleted

FROM events
GROUP BY date, actor_id;
```

### ChromaDB Schema (Vector Store)

```python
# vector_store/collections.py
import chromadb
from chromadb.utils import embedding_functions

# Initialize ChromaDB
client = chromadb.PersistentClient(path="./chroma_db")

# Embedding function (use OpenAI or local model)
embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
    api_key=OPENAI_API_KEY,
    model_name="text-embedding-3-small"
)

# Collection 1: Developer Profiles
developer_profiles = client.get_or_create_collection(
    name="developer_profiles",
    embedding_function=embedding_fn,
    metadata={"description": "Developer skills and expertise profiles"}
)

# Example: Adding a developer profile
def add_developer_profile(user_id: str, profile_text: str, metadata: dict):
    """
    profile_text example:
    "Senior Python developer with 5 years experience. 
     Expertise in FastAPI, PostgreSQL, machine learning. 
     Contributed to data pipeline, ML inference service, API gateway.
     Languages: Python (expert), Go (intermediate), JavaScript (basic).
     Frameworks: FastAPI, Django, TensorFlow, LangChain."
    """
    developer_profiles.add(
        ids=[user_id],
        documents=[profile_text],
        metadatas=[metadata]  # {"team": "ML", "level": "senior", ...}
    )

# Query for matching developers
def find_matching_developers(project_requirements: str, top_k: int = 5):
    results = developer_profiles.query(
        query_texts=[project_requirements],
        n_results=top_k
    )
    return results

# Collection 2: Project Documentation
project_docs = client.get_or_create_collection(
    name="project_documentation",
    embedding_function=embedding_fn,
    metadata={"description": "Project docs, READMEs, architecture decisions"}
)
```

### Neo4j Schema (Optional - For Complex Relationships)

```cypher
// Node definitions
CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE;

// Example relationships
// User belongs to Team
(:User)-[:BELONGS_TO]->(:Team)

// User contributes to Project
(:User)-[:CONTRIBUTES_TO {role: "maintainer", since: date}]->(:Project)

// Project depends on Project
(:Project)-[:DEPENDS_ON]->(:Project)

// Team owns Project
(:Team)-[:OWNS]->(:Project)

// Useful queries
// Find all developers who could be affected by Project X delay
MATCH (p:Project {name: "Project X"})<-[:DEPENDS_ON*1..3]-(downstream:Project)<-[:CONTRIBUTES_TO]-(u:User)
RETURN DISTINCT u.name, downstream.name

// Find the best developer for a new ML project
MATCH (u:User)-[:CONTRIBUTES_TO]->(p:Project)
WHERE p.tech_stack CONTAINS "Python" AND p.domain = "ML"
WITH u, COUNT(p) as ml_projects
ORDER BY ml_projects DESC
LIMIT 5
RETURN u.name, ml_projects
```

---

## 4. AI/ML Layer Architecture

### Multi-Agent System Design (LangGraph)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AI/ML LAYER ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     SUPERVISOR AGENT                                 │   │
│  │  Orchestrates all sub-agents, routes queries, manages state         │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│         ┌───────────┬───────────┼───────────┬───────────┬───────────┐      │
│         ▼           ▼           ▼           ▼           ▼           ▼      │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐     │
│  │  Metrics  │ │  RAG      │ │ Anomaly   │ │ Forecast  │ │ Recommend │     │
│  │  Agent    │ │  Agent    │ │ Agent     │ │ Agent     │ │ Agent     │     │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘     │
│       │             │             │             │             │             │
│       ▼             ▼             ▼             ▼             ▼             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        TOOL LAYER                                    │   │
│  │  MCP Clients | DB Queries | Prometheus | Embeddings | ML Models     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Definitions

```python
# agents/supervisor.py
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    query: str
    context: dict
    messages: Annotated[list, operator.add]
    next_agent: str
    final_response: str

# Define the supervisor
def supervisor_node(state: AgentState):
    """Route to appropriate agent based on query"""
    
    query = state["query"].lower()
    
    if any(word in query for word in ["dora", "velocity", "cycle time", "metrics"]):
        return {"next_agent": "metrics_agent"}
    elif any(word in query for word in ["who", "developer", "engineer", "match", "suitable"]):
        return {"next_agent": "rag_agent"}
    elif any(word in query for word in ["unusual", "anomaly", "spike", "drop"]):
        return {"next_agent": "anomaly_agent"}
    elif any(word in query for word in ["predict", "forecast", "when", "estimate"]):
        return {"next_agent": "forecast_agent"}
    elif any(word in query for word in ["suggest", "recommend", "should", "improve"]):
        return {"next_agent": "recommend_agent"}
    else:
        return {"next_agent": "rag_agent"}  # Default to RAG
```

### Specialized Agents

#### 1. Metrics Agent

```python
# agents/metrics_agent.py
from langchain_core.tools import tool

@tool
def calculate_dora_metrics(project_id: str, time_range_days: int = 30) -> dict:
    """Calculate DORA metrics for a project"""
    
    # Query ClickHouse
    query = f"""
    SELECT 
        sum(deployment_count) as deployments,
        avg(avg_lead_time_seconds) / 3600 as lead_time_hours,
        sum(failed_deployments) / sum(deployment_count) as change_failure_rate
    FROM dora_daily_metrics
    WHERE project_id = '{project_id}'
      AND date >= today() - {time_range_days}
    """
    result = clickhouse_client.execute(query)
    
    # Calculate deployment frequency
    deployments = result[0][0]
    deployment_frequency = deployments / time_range_days
    
    return {
        "deployment_frequency": f"{deployment_frequency:.2f} deploys/day",
        "lead_time_for_changes": f"{result[0][1]:.1f} hours",
        "change_failure_rate": f"{result[0][2]*100:.1f}%",
        "rating": classify_dora_performance(deployment_frequency, result[0][1], result[0][2])
    }

@tool
def get_sprint_velocity(project_key: str, num_sprints: int = 5) -> dict:
    """Get sprint velocity trend"""
    
    # Use MCP to fetch from Jira
    velocity_data = await jira_mcp_client.call_tool(
        "get_velocity_history",
        {"project_key": project_key, "limit": num_sprints}
    )
    
    velocities = [s["velocity"] for s in velocity_data]
    
    return {
        "velocities": velocity_data,
        "average": sum(velocities) / len(velocities),
        "trend": "increasing" if velocities[-1] > velocities[0] else "decreasing"
    }
```

#### 2. RAG Agent (Developer Matching)

```python
# agents/rag_agent.py

@tool
def find_best_developers_for_project(
    project_requirements: str,
    required_availability_percent: float = 30.0,
    top_k: int = 5
) -> list:
    """Find developers matching project requirements with availability"""
    
    # Step 1: Semantic search in vector DB
    semantic_matches = developer_profiles.query(
        query_texts=[project_requirements],
        n_results=top_k * 2  # Get more to filter by availability
    )
    
    results = []
    for i, (id, distance) in enumerate(zip(
        semantic_matches['ids'][0], 
        semantic_matches['distances'][0]
    )):
        # Step 2: Check availability via MCP
        workload = await jira_mcp_client.call_tool(
            "get_developer_workload",
            {"developer_email": semantic_matches['metadatas'][0][i]['email']}
        )
        
        # Calculate availability (assuming 40 story points = 100% capacity)
        current_load = workload['total_story_points']
        availability = max(0, (40 - current_load) / 40 * 100)
        
        if availability >= required_availability_percent:
            results.append({
                "developer": semantic_matches['metadatas'][0][i],
                "match_score": 1 - distance,  # Convert distance to similarity
                "availability_percent": availability,
                "current_workload": workload
            })
        
        if len(results) >= top_k:
            break
    
    return results
```

#### 3. Anomaly Detection Agent

```python
# agents/anomaly_agent.py
import numpy as np
from scipy import stats

@tool
def detect_metric_anomalies(
    project_id: str,
    metric_name: str,
    lookback_days: int = 30
) -> dict:
    """Detect anomalies in a metric using statistical methods"""
    
    # Fetch historical data
    query = f"""
    SELECT date, {metric_name}
    FROM dora_daily_metrics
    WHERE project_id = '{project_id}'
      AND date >= today() - {lookback_days}
    ORDER BY date
    """
    data = clickhouse_client.execute(query)
    
    values = [row[1] for row in data]
    dates = [row[0] for row in data]
    
    # Z-score based anomaly detection
    mean = np.mean(values)
    std = np.std(values)
    z_scores = [(v - mean) / std for v in values]
    
    anomalies = []
    for i, z in enumerate(z_scores):
        if abs(z) > 2.5:  # Threshold
            anomalies.append({
                "date": dates[i].isoformat(),
                "value": values[i],
                "z_score": z,
                "type": "spike" if z > 0 else "drop"
            })
    
    return {
        "metric": metric_name,
        "mean": mean,
        "std_dev": std,
        "anomalies": anomalies,
        "severity": "high" if len(anomalies) > 3 else "medium" if anomalies else "none"
    }
```

#### 4. Forecast Agent

```python
# agents/forecast_agent.py
from prophet import Prophet
import pandas as pd

@tool
def forecast_project_completion(
    project_id: str,
    remaining_story_points: int
) -> dict:
    """Predict project completion date based on historical velocity"""
    
    # Get historical velocity
    query = f"""
    SELECT 
        toMonday(timestamp) as week,
        sumIf(JSONExtractInt(metadata, 'story_points'), event_type = 'issue_completed') as points
    FROM events
    WHERE project_id = '{project_id}'
    GROUP BY week
    ORDER BY week
    """
    data = clickhouse_client.execute(query)
    
    df = pd.DataFrame(data, columns=['ds', 'y'])
    
    # Train Prophet model
    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=False
    )
    model.fit(df)
    
    # Forecast until remaining points are completed
    future = model.make_future_dataframe(periods=26, freq='W')
    forecast = model.predict(future)
    
    # Calculate completion date
    cumulative_velocity = 0
    predicted_completion = None
    for _, row in forecast.iterrows():
        if row['ds'] > df['ds'].max():
            cumulative_velocity += max(0, row['yhat'])
            if cumulative_velocity >= remaining_story_points:
                predicted_completion = row['ds']
                break
    
    return {
        "remaining_points": remaining_story_points,
        "average_weekly_velocity": df['y'].mean(),
        "predicted_completion_date": predicted_completion.strftime("%Y-%m-%d") if predicted_completion else "Beyond forecast range",
        "confidence_interval": {
            "optimistic": (remaining_story_points / forecast['yhat_upper'].mean()),
            "pessimistic": (remaining_story_points / forecast['yhat_lower'].mean())
        }
    }
```

#### 5. Recommendation Agent

```python
# agents/recommend_agent.py

@tool
def generate_improvement_recommendations(project_id: str) -> list:
    """Generate actionable recommendations based on project health"""
    
    recommendations = []
    
    # Get DORA metrics
    dora = await calculate_dora_metrics(project_id)
    
    # Check deployment frequency
    if "low" in dora["rating"].lower():
        if dora["deployment_frequency"] < 1:
            recommendations.append({
                "area": "Deployment Frequency",
                "severity": "high",
                "issue": f"Deploying only {dora['deployment_frequency']} times/day",
                "recommendation": "Implement trunk-based development and feature flags",
                "expected_impact": "2-3x increase in deployment frequency"
            })
    
    # Check lead time
    lead_time_hours = float(dora["lead_time_for_changes"].split()[0])
    if lead_time_hours > 24:
        recommendations.append({
            "area": "Lead Time",
            "severity": "medium",
            "issue": f"Lead time is {lead_time_hours:.0f} hours",
            "recommendation": "Reduce PR size, automate testing, streamline reviews",
            "expected_impact": "50% reduction in lead time"
        })
    
    # Check change failure rate
    cfr = float(dora["change_failure_rate"].rstrip('%'))
    if cfr > 15:
        recommendations.append({
            "area": "Quality",
            "severity": "high",
            "issue": f"Change failure rate is {cfr}%",
            "recommendation": "Increase test coverage, add staging environment",
            "expected_impact": "Reduce failures to <5%"
        })
    
    return recommendations
```

### LangGraph Workflow

```python
# agents/workflow.py
from langgraph.graph import StateGraph, END

# Build the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("metrics_agent", metrics_agent_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("anomaly_agent", anomaly_agent_node)
workflow.add_node("forecast_agent", forecast_agent_node)
workflow.add_node("recommend_agent", recommend_agent_node)
workflow.add_node("synthesizer", synthesize_response_node)

# Add edges
workflow.set_entry_point("supervisor")

workflow.add_conditional_edges(
    "supervisor",
    lambda x: x["next_agent"],
    {
        "metrics_agent": "metrics_agent",
        "rag_agent": "rag_agent",
        "anomaly_agent": "anomaly_agent",
        "forecast_agent": "forecast_agent",
        "recommend_agent": "recommend_agent",
    }
)

# All agents route to synthesizer
for agent in ["metrics_agent", "rag_agent", "anomaly_agent", "forecast_agent", "recommend_agent"]:
    workflow.add_edge(agent, "synthesizer")

workflow.add_edge("synthesizer", END)

# Compile
app = workflow.compile()
```

---

## 5. Presentation Layer Architecture

### Role-Based Dashboard Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      API GATEWAY (FastAPI)                           │   │
│  │  /api/v1/metrics | /api/v1/insights | /api/v1/query | /api/v1/ws   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│  ┌────────────────────────────────┴────────────────────────────────────┐   │
│  │                     FRONTEND (Next.js / React)                       │   │
│  │                                                                      │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │   │
│  │  │ Engineering  │ │ Product      │ │ HR           │ │ Executive   │ │   │
│  │  │ Dashboard    │ │ Dashboard    │ │ Dashboard    │ │ Dashboard   │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐│   │
│  │  │              NATURAL LANGUAGE QUERY INTERFACE                   ││   │
│  │  │  "Why is Project Alpha delayed?" → AI-powered answer            ││   │
│  │  └─────────────────────────────────────────────────────────────────┘│   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dashboard Specifications by Role

#### Engineering Lead Dashboard

| Component | Widget Type | Data Source | Refresh Rate |
|-----------|-------------|-------------|--------------|
| DORA Metrics | KPI Cards | ClickHouse | 5 min |
| Sprint Burndown | Line Chart | Jira MCP | 15 min |
| PR Queue | Table | GitHub API | Real-time |
| Build Status | Status Grid | Prometheus | 1 min |
| Team Velocity | Bar Chart | ClickHouse | Daily |
| Code Review Time | Histogram | ClickHouse | Hourly |

#### Product Manager Dashboard

| Component | Widget Type | Data Source | Refresh Rate |
|-----------|-------------|-------------|--------------|
| Feature Progress | Progress Bars | Jira MCP | 15 min |
| Roadmap Timeline | Gantt Chart | Notion + Forecast | Daily |
| Release Readiness | Checklist | Multi-source | 30 min |
| Dependency Risks | Risk Matrix | Neo4j | Hourly |
| Customer Impact | KPI Cards | Custom | Daily |

#### HR Dashboard

| Component | Widget Type | Data Source | Refresh Rate |
|-----------|-------------|-------------|--------------|
| Team Utilization | Heat Map | Jira + HRIS | Daily |
| Skill Distribution | Radar Chart | Vector DB | Weekly |
| Developer Matching | Search + Results | RAG Agent | On-demand |
| Burnout Risk | Alert Cards | Multi-source | Daily |
| Hiring Recommendations | Table | AI Analysis | Weekly |

#### Executive Dashboard

| Component | Widget Type | Data Source | Refresh Rate |
|-----------|-------------|-------------|--------------|
| Portfolio Health | RAG Status Grid | Aggregated | Hourly |
| Engineering ROI | KPI Cards | ClickHouse + Finance | Daily |
| Risk Radar | Bubble Chart | AI Analysis | Daily |
| Top Recommendations | Action Cards | Recommend Agent | Daily |
| Cost Trends | Line Chart | ClickHouse | Daily |

### API Endpoints

```python
# api/routes.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Engineering Intelligence API")

# Metrics endpoints
@app.get("/api/v1/metrics/dora/{project_id}")
async def get_dora_metrics(project_id: str, days: int = 30):
    """Get DORA metrics for a project"""
    return await metrics_service.get_dora(project_id, days)

@app.get("/api/v1/metrics/velocity/{project_key}")
async def get_velocity(project_key: str, sprints: int = 5):
    """Get sprint velocity history"""
    return await metrics_service.get_velocity(project_key, sprints)

# AI query endpoint
@app.post("/api/v1/query")
async def natural_language_query(query: QueryRequest):
    """Process natural language query through AI agents"""
    result = await agent_workflow.invoke({
        "query": query.text,
        "context": {"user_role": query.user_role}
    })
    return {"answer": result["final_response"]}

# Developer matching
@app.post("/api/v1/developers/match")
async def match_developers(requirements: MatchRequest):
    """Find developers matching project requirements"""
    return await rag_agent.find_best_developers(
        requirements.description,
        requirements.availability_threshold
    )

# WebSocket for real-time updates
@app.websocket("/api/v1/ws/dashboard/{user_id}")
async def dashboard_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    async for event in event_stream.subscribe(user_id):
        await websocket.send_json(event)

# Forecasting
@app.get("/api/v1/forecast/completion/{project_id}")
async def forecast_completion(project_id: str):
    """Predict project completion date"""
    return await forecast_agent.predict_completion(project_id)

# Recommendations
@app.get("/api/v1/recommendations/{project_id}")
async def get_recommendations(project_id: str):
    """Get AI-powered improvement recommendations"""
    return await recommend_agent.generate(project_id)
```

### Natural Language Query Interface

```typescript
// frontend/components/QueryInterface.tsx
import { useState } from 'react';

export function QueryInterface() {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleQuery = async () => {
    setLoading(true);
    const res = await fetch('/api/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        text: query,
        user_role: currentUser.role 
      })
    });
    const data = await res.json();
    setResponse(data.answer);
    setLoading(false);
  };

  return (
    <div className="query-interface">
      <input
        type="text"
        placeholder="Ask anything... e.g., 'Why is Project Alpha delayed?'"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
      />
      <button onClick={handleQuery} disabled={loading}>
        {loading ? 'Thinking...' : 'Ask AI'}
      </button>
      
      {response && (
        <div className="response">
          <ReactMarkdown>{response}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
```

### Example Query Flows

**Query 1:** "Why is Project Alpha behind schedule?"

```
User → Supervisor Agent → Metrics Agent (get DORA, velocity)
                       → Anomaly Agent (check for spikes)
                       → RAG Agent (search project docs)
     → Synthesizer → Response:

"Project Alpha is 2 weeks behind due to:
1. **Velocity Drop**: Sprint 14 velocity was 28 pts vs 42 pt average (33% drop)
2. **Blocked Issues**: 5 issues blocked for >3 days waiting on API team
3. **Increased Bug Rate**: 12 bugs filed post-sprint 13, double the normal rate

Recommendations:
- Prioritize API team blockers
- Schedule bug bash before next sprint
- Consider scope reduction for MVP"
```

**Query 2:** "Who should work on our new ML project?"

```
User → Supervisor Agent → RAG Agent (semantic search developers)
                       → Jira MCP (check availability)
     → Synthesizer → Response:

"Top 3 matching developers for ML project:

1. **Sarah Chen** (94% match, 60% available)
   - 3 years ML experience, TensorFlow expert
   - Contributed to: recommendation-engine, fraud-detection
   
2. **Mike Johnson** (87% match, 40% available)
   - 2 years ML, strong Python
   - Currently 60% allocated to data-pipeline project
   
3. **Alex Kim** (82% match, 80% available)
   - 1 year ML, learning trajectory strong
   - Finishing up on analytics-dashboard next sprint"
```

---

## 6. Technology Stack Summary

### For Hackathon (48-72 hours)

| Layer | Technology | Justification |
|-------|------------|---------------|
| **Backend** | FastAPI (Python) | Fast development, async support |
| **Database - Primary** | SQLite/PostgreSQL | Simple setup |
| **Database - Time Series** | TimescaleDB | PostgreSQL extension |
| **Database - Vector** | ChromaDB | Local, no cloud dependency |
| **Event Queue** | Redis Streams | Simpler than Kafka |
| **AI/LLM** | Claude API / GPT-4 | Pre-built, no training |
| **Agent Framework** | LangGraph | Native multi-agent support |
| **Frontend** | Next.js + Tailwind | Rapid UI development |
| **Charts** | Recharts / Tremor | React-native, beautiful |

### For Production

| Layer | Technology | Justification |
|-------|------------|---------------|
| **Backend** | FastAPI + Go microservices | Scale-out |
| **Database - Primary** | PostgreSQL (RDS) | Managed, reliable |
| **Database - Time Series** | ClickHouse | 100x faster aggregations |
| **Database - Vector** | Pinecone | Managed, scalable |
| **Database - Graph** | Neo4j | Complex relationship queries |
| **Event Streaming** | Apache Kafka | Enterprise-grade |
| **AI/LLM** | Claude Enterprise | Data privacy, SLAs |
| **Monitoring** | Prometheus + Grafana | Industry standard |
| **Frontend** | Next.js + Enterprise UI | Production-ready |

---

## 7. Team Work Distribution

### Member 1: Data Ingestion Layer

**Deliverables:**
- [ ] GitHub webhook receiver
- [ ] Jira webhook receiver
- [ ] Event normalization service
- [ ] Polling service for historical sync
- [ ] MCP server for Jira
- [ ] MCP server for GitHub

**Key Files:**
```
src/
├── ingestion/
│   ├── webhooks/
│   │   ├── github_handler.py
│   │   └── jira_handler.py
│   ├── polling/
│   │   └── scheduler.py
│   ├── mcp_servers/
│   │   ├── jira_server.py
│   │   └── github_server.py
│   └── normalizers/
│       └── event_normalizer.py
```

---

### Member 2: Database Layer

**Deliverables:**
- [ ] PostgreSQL schema + migrations
- [ ] ClickHouse schema + materialized views
- [ ] ChromaDB collection setup
- [ ] Identity resolution service
- [ ] Data access layer (repositories)

**Key Files:**
```
src/
├── database/
│   ├── postgres/
│   │   ├── models.py
│   │   ├── migrations/
│   │   └── repositories.py
│   ├── clickhouse/
│   │   ├── schema.sql
│   │   └── queries.py
│   ├── vector/
│   │   └── collections.py
│   └── identity/
│       └── resolver.py
```

---

### Member 3: AI/ML Layer

**Deliverables:**
- [ ] LangGraph workflow definition
- [ ] Supervisor agent
- [ ] Metrics agent + tools
- [ ] RAG agent + embeddings pipeline
- [ ] Anomaly detection agent
- [ ] Forecast agent
- [ ] Recommendation agent

**Key Files:**
```
src/
├── agents/
│   ├── supervisor.py
│   ├── metrics_agent.py
│   ├── rag_agent.py
│   ├── anomaly_agent.py
│   ├── forecast_agent.py
│   ├── recommend_agent.py
│   ├── tools/
│   │   ├── dora_tools.py
│   │   ├── developer_tools.py
│   │   └── forecast_tools.py
│   └── workflow.py
```

---

### Member 4: Presentation Layer

**Deliverables:**
- [ ] FastAPI routes
- [ ] WebSocket real-time updates
- [ ] Engineering Lead dashboard
- [ ] Executive dashboard
- [ ] HR/Developer matching UI
- [ ] Natural language query interface

**Key Files:**
```
src/
├── api/
│   ├── routes/
│   │   ├── metrics.py
│   │   ├── query.py
│   │   ├── developers.py
│   │   └── websocket.py
│   └── main.py
frontend/
├── components/
│   ├── dashboards/
│   │   ├── EngineeringDashboard.tsx
│   │   ├── ExecutiveDashboard.tsx
│   │   └── HRDashboard.tsx
│   ├── QueryInterface.tsx
│   └── charts/
```

---

## 8. Integration Points

### Member 1 ↔ Member 2
- Normalized events → ClickHouse insertion
- Raw events → PostgreSQL for debugging

### Member 2 ↔ Member 3
- ClickHouse queries via repository pattern
- Vector DB queries for RAG

### Member 3 ↔ Member 4
- Agent workflow invocation via API
- Structured responses for dashboards

### Member 1 ↔ Member 3
- MCP servers used by RAG agent
- Real-time context fetching

---

*Document ready for team distribution. Each member should create their feature branch and integrate at defined interfaces.*
