# Cloud Database Architecture: AWS-Based Deployment

> **Complete Cloud Infrastructure Guide**
>
> Everything cloud-hosted, interconnected for AI agents

---

## Cloud Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CLOUD ARCHITECTURE OVERVIEW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        DATA SOURCES                                   │  │
│  │   GitHub Webhooks │ Jira Webhooks │ Notion API │ Prometheus API      │  │
│  └─────────────────────────────┬────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │              AWS API GATEWAY + LAMBDA (Webhook Receivers)            │  │
│  └─────────────────────────────┬────────────────────────────────────────┘  │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      AMAZON SQS (Event Queue)                        │  │
│  └─────────────────────────────┬────────────────────────────────────────┘  │
│                                │                                            │
│         ┌──────────────────────┼──────────────────────┐                    │
│         ▼                      ▼                      ▼                    │
│  ┌─────────────┐      ┌─────────────┐      ┌────────────────┐              │
│  │ Aurora      │      │ ClickHouse  │      │ Pinecone       │              │
│  │ PostgreSQL  │      │ Cloud       │      │ (Vector DB)    │              │
│  │ (AWS RDS)   │      │ (AWS Market)│      │                │              │
│  └─────────────┘      └─────────────┘      └────────────────┘              │
│         │                    │                      │                      │
│         └────────────────────┼──────────────────────┘                      │
│                              │                                              │
│                    ┌─────────┴─────────┐                                   │
│                    │   Neo4j Aura     │                                    │
│                    │   (Graph DB)     │                                    │
│                    └──────────────────┘                                    │
│                              │                                              │
│                              ▼                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │            UNIFIED DATA ACCESS LAYER (Lambda / ECS)                  │  │
│  │                  AI Agents Query Any Database                        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Recommendations

| Purpose | Service | Why This Choice | Cost Estimate |
|---------|---------|-----------------|---------------|
| **Primary DB** | AWS Aurora PostgreSQL | Managed, auto-scaling, AWS native | ~$30-50/mo (serverless) |
| **Time-Series** | ClickHouse Cloud | 100x faster analytics than Postgres | ~$67/mo (basic tier) |
| **Vector DB** | Pinecone | Serverless, no infra management | Free tier (100K vectors) |
| **Graph DB** | Neo4j Aura | Free tier, Cypher query language | Free (50K nodes limit) |

---

## 1. Aurora PostgreSQL (Primary Database)

### Purpose
Store entities, relationships, user data, and identity mappings.

### Setup Steps
```bash
# Via AWS Console or CLI
aws rds create-db-cluster \
  --db-cluster-identifier engineering-intelligence \
  --engine aurora-postgresql \
  --engine-version 15.4 \
  --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=4 \
  --master-username admin \
  --master-user-password YOUR_PASSWORD \
  --vpc-security-group-ids sg-xxx
```

### Schema (from GitHub, Jira, Notion, Prometheus)

```sql
-- Users (identity resolution across all sources)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    team_id UUID REFERENCES teams(id),
    hourly_rate DECIMAL(10,2),  -- For cost calculations
    created_at TIMESTAMP DEFAULT NOW()
);

-- Identity mappings (link GitHub/Jira/Slack usernames to users)
CREATE TABLE identity_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    source VARCHAR(50) NOT NULL,  -- 'github', 'jira', 'notion'
    external_id VARCHAR(255) NOT NULL,
    external_username VARCHAR(255),
    UNIQUE(source, external_id)
);

-- Projects (from GitHub repos, Jira projects, Notion databases)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    github_repo VARCHAR(255),      -- From GitHub
    jira_project_key VARCHAR(50),  -- From Jira
    notion_database_id VARCHAR(50),-- From Notion
    status VARCHAR(50) DEFAULT 'active',
    priority VARCHAR(20),
    target_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Teams
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    manager_id UUID REFERENCES users(id)
);

-- Project assignments
CREATE TABLE project_assignments (
    user_id UUID REFERENCES users(id),
    project_id UUID REFERENCES projects(id),
    role VARCHAR(50),  -- 'lead', 'contributor', 'reviewer'
    allocated_percent DECIMAL(5,2),
    PRIMARY KEY(user_id, project_id)
);
```

### Connection from Lambda/ECS

```python
import boto3
from sqlalchemy import create_engine

# Use Secrets Manager for credentials
secrets = boto3.client('secretsmanager')
creds = secrets.get_secret_value(SecretId='aurora-credentials')

engine = create_engine(
    f"postgresql://{creds['username']}:{creds['password']}@"
    f"{creds['host']}:5432/engineering_intelligence"
)
```

---

## 2. ClickHouse Cloud (Time-Series Analytics)

### Purpose
Store high-volume events, metrics, and pre-computed aggregations from all sources.

### Setup Steps

1. **Sign up at** [clickhouse.cloud](https://clickhouse.cloud)
2. **Create Service** → Select AWS, choose region (us-east-1 recommended)
3. **Choose Basic Tier** ($67/month or use trial credits)
4. **Get Connection Details** → Host, port, username, password

### Data Model (What goes here from each source)

```sql
-- Raw events from all sources (partitioned by day)
CREATE TABLE events (
    event_id UUID,
    timestamp DateTime,
    
    -- Source identification
    source LowCardinality(String),     -- 'github', 'jira', 'notion', 'prometheus'
    event_type LowCardinality(String), -- 'commit', 'pr_merged', 'issue_updated', etc.
    
    -- Entity identification
    project_id String,
    actor_id String,           -- user email or username
    entity_id String,          -- issue key, commit SHA, PR number
    entity_type LowCardinality(String),
    
    -- Metadata (source-specific, stored as JSON)
    metadata String,
    
    INDEX idx_project project_id TYPE bloom_filter GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (source, event_type, timestamp);
```

### What data comes from each source?

```sql
-- GITHUB EVENTS (via webhooks)
-- event_types: 'commit', 'pr_opened', 'pr_merged', 'pr_reviewed', 'workflow_run'
-- metadata includes: lines_added, lines_deleted, review_time_hours, build_status

-- JIRA EVENTS (via webhooks)  
-- event_types: 'issue_created', 'issue_updated', 'issue_completed', 'sprint_started', 'sprint_closed'
-- metadata includes: story_points, status_from, status_to, blocked_time_hours

-- NOTION EVENTS (via polling)
-- event_types: 'page_created', 'page_updated', 'database_item_created'
-- metadata includes: page_title, database_name, properties

-- PROMETHEUS METRICS (via polling)
-- event_types: 'metric_sample'
-- metadata includes: metric_name, value, labels
```

### Pre-computed DORA Metrics View

```sql
CREATE MATERIALIZED VIEW dora_daily_metrics
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(date)
ORDER BY (project_id, date)
AS SELECT
    toDate(timestamp) as date,
    project_id,
    
    -- From GitHub workflow_run events
    countIf(event_type = 'deployment' OR 
            (event_type = 'workflow_run' AND JSONExtractString(metadata, 'conclusion') = 'success'))
        as deployments,
    
    -- Lead time (from Jira + GitHub)
    avgIf(JSONExtractFloat(metadata, 'lead_time_hours'), event_type = 'pr_merged') 
        as avg_lead_time_hours,
    
    -- From GitHub/Jira
    countIf(event_type = 'pr_merged') as prs_merged,
    sumIf(JSONExtractInt(metadata, 'story_points'), event_type = 'issue_completed') 
        as story_points_completed
        
FROM events
GROUP BY date, project_id;
```

### Connection from Lambda

```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host='xxx.aws.clickhouse.cloud',
    port=8443,
    username='default',
    password='YOUR_PASSWORD',
    secure=True
)

# Query example
result = client.query('''
    SELECT project_id, sum(deployments) as total_deploys
    FROM dora_daily_metrics
    WHERE date >= today() - 30
    GROUP BY project_id
''')
```

---

## 3. Pinecone (Vector Database)

### Purpose
Store embeddings for semantic search: developer profiles, project documentation, skill matching.

### Setup Steps

1. **Sign up at** [pinecone.io](https://www.pinecone.io)
2. **Create Index** → Name: `engineering-intelligence`
3. **Configuration:**
   - Dimension: 1024 (for llama-text-embed-v2)
   - Metric: cosine
   - Cloud: AWS, Region: us-east-1

### Data Model

```python
# Two namespaces in one index

# Namespace 1: developer_profiles
{
    "id": "user_uuid",
    "values": [0.1, 0.2, ...],  # 1024-dim embedding
    "metadata": {
        "email": "john@company.com",
        "name": "John Doe",
        "team": "Platform",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "github_repos": ["api-gateway", "data-pipeline"],
        "jira_projects": ["PLAT", "DATA"],  # From Jira
        "total_commits_30d": 45,             # From GitHub
        "avg_pr_review_time_hours": 4.2      # From GitHub
    }
}

# Namespace 2: project_docs
{
    "id": "doc_chunk_uuid",
    "values": [0.1, 0.2, ...],
    "metadata": {
        "project_id": "proj_uuid",
        "source": "notion",  # or "github_readme"
        "title": "API Gateway Architecture",
        "chunk_index": 0
    }
}
```

### Connection from Lambda

```python
from pinecone import Pinecone
import os

pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
index = pc.Index("engineering-intelligence")

# Query for matching developers
def find_developers(project_requirements: str, embedding: list, top_k: int = 5):
    results = index.query(
        namespace="developer_profiles",
        vector=embedding,
        top_k=top_k,
        include_metadata=True
    )
    return results.matches
```

### What data feeds Pinecone?

| Source | What Gets Embedded | Namespace |
|--------|-------------------|-----------|
| **GitHub** | README content, developer contribution summaries | project_docs, developer_profiles |
| **Jira** | Epic descriptions, project goals | project_docs |
| **Notion** | Page content, documentation | project_docs |
| **Computed** | Developer skill profiles (from all sources) | developer_profiles |

---

## 4. Neo4j Aura (Graph Database)

### Purpose
Model complex relationships: team structures, project dependencies, developer-to-project connections.

### Setup Steps

1. **Go to** [console.neo4j.io](https://console.neo4j.io)
2. **Create Instance** → Select "Free" tier
3. **Save credentials** (username: neo4j, password: auto-generated)
4. **Note connection URI** (neo4j+s://xxx.databases.neo4j.io)

> [!TIP]
> **Free Tier Limits:** 50,000 nodes, 175,000 relationships — plenty for a hackathon!

### Data Model

```cypher
// Nodes (from various sources)
(:User {id, email, name, team})           // From HRIS + identity resolution
(:Team {id, name})                        // From HRIS
(:Project {id, name, jira_key, github_repo})  // From Jira + GitHub
(:Skill {name})                           // From GitHub language detection

// Relationships
(:User)-[:BELONGS_TO]->(:Team)
(:User)-[:CONTRIBUTES_TO {commits: 45, prs: 12}]->(:Project)  // From GitHub
(:User)-[:HAS_SKILL {level: 'expert'}]->(:Skill)              // From GitHub
(:Project)-[:DEPENDS_ON]->(:Project)                          // From Notion/manual
(:Team)-[:OWNS]->(:Project)                                   // From Jira
```

### Example Queries

```cypher
// Find all developers affected if Project X is delayed (via dependencies)
MATCH (p:Project {name: "Project X"})<-[:DEPENDS_ON*1..3]-(downstream:Project)
      <-[:CONTRIBUTES_TO]-(u:User)
RETURN DISTINCT u.name, downstream.name

// Find developers with Python skills available for new project
MATCH (u:User)-[:HAS_SKILL {level: 'expert'}]->(:Skill {name: 'Python'})
WHERE NOT (u)-[:CONTRIBUTES_TO]->(:Project {status: 'active'})
RETURN u.name, u.email

// Get team workload distribution
MATCH (t:Team)<-[:BELONGS_TO]-(u:User)-[c:CONTRIBUTES_TO]->(p:Project)
RETURN t.name, COUNT(DISTINCT u) as developers, SUM(c.commits) as total_commits
```

### Connection from Lambda

```python
from neo4j import GraphDatabase
import os

driver = GraphDatabase.driver(
    os.environ['NEO4J_URI'],
    auth=("neo4j", os.environ['NEO4J_PASSWORD'])
)

def get_project_dependencies(project_name: str):
    with driver.session() as session:
        result = session.run('''
            MATCH (p:Project {name: $name})<-[:DEPENDS_ON*1..3]-(d:Project)
            RETURN d.name as dependency
        ''', name=project_name)
        return [r['dependency'] for r in result]
```

---

## 5. Data Ingestion Architecture

### Webhook Receiver (AWS Lambda + API Gateway)

```
GitHub/Jira Webhook → API Gateway → Lambda → SQS → Processing Lambda → DBs
```

#### Lambda Handler (Webhook Receiver)

```python
# webhook_receiver/handler.py
import json
import boto3
import hashlib
import hmac
import os

sqs = boto3.client('sqs')
QUEUE_URL = os.environ['EVENT_QUEUE_URL']

def github_webhook(event, context):
    """Receive and validate GitHub webhook"""
    
    # Validate signature
    signature = event['headers'].get('x-hub-signature-256', '')
    body = event['body']
    
    expected = 'sha256=' + hmac.new(
        os.environ['GITHUB_WEBHOOK_SECRET'].encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        return {'statusCode': 401, 'body': 'Invalid signature'}
    
    # Normalize event
    event_type = event['headers'].get('x-github-event')
    payload = json.loads(body)
    
    normalized = {
        'source': 'github',
        'event_type': event_type,
        'payload': payload,
        'timestamp': payload.get('created_at') or payload.get('pushed_at')
    }
    
    # Send to SQS for async processing
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(normalized)
    )
    
    return {'statusCode': 200, 'body': 'OK'}

def jira_webhook(event, context):
    """Receive Jira webhook"""
    payload = json.loads(event['body'])
    
    normalized = {
        'source': 'jira',
        'event_type': payload.get('webhookEvent'),
        'payload': payload,
        'timestamp': payload.get('timestamp')
    }
    
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(normalized)
    )
    
    return {'statusCode': 200, 'body': 'OK'}
```

#### Event Processing Lambda

```python
# event_processor/handler.py
import json
from datetime import datetime
from db_clients import aurora, clickhouse, pinecone_client, neo4j

def process_event(event, context):
    """Process events from SQS and write to appropriate databases"""
    
    for record in event['Records']:
        msg = json.loads(record['body'])
        source = msg['source']
        event_type = msg['event_type']
        payload = msg['payload']
        
        # 1. Always write raw event to ClickHouse (time-series)
        write_to_clickhouse(msg)
        
        # 2. Conditionally update other databases
        if source == 'github':
            if event_type == 'push':
                update_developer_stats(payload)  # Aurora
                update_developer_embedding(payload)  # Pinecone
                update_contribution_graph(payload)  # Neo4j
            elif event_type == 'pull_request':
                if payload['action'] == 'closed' and payload['pull_request']['merged']:
                    update_pr_metrics(payload)  # ClickHouse aggregate
                    
        elif source == 'jira':
            if event_type == 'issue_updated':
                sync_project_status(payload)  # Aurora
                update_workload_graph(payload)  # Neo4j

def write_to_clickhouse(msg):
    """Write normalized event to ClickHouse"""
    clickhouse.command('''
        INSERT INTO events (event_id, timestamp, source, event_type, 
                           project_id, actor_id, entity_id, metadata)
        VALUES (generateUUIDv4(), now(), %(source)s, %(event_type)s,
                %(project_id)s, %(actor_id)s, %(entity_id)s, %(metadata)s)
    ''', parameters={
        'source': msg['source'],
        'event_type': msg['event_type'],
        'project_id': extract_project_id(msg),
        'actor_id': extract_actor_id(msg),
        'entity_id': extract_entity_id(msg),
        'metadata': json.dumps(msg['payload'])
    })
```

### Polling Service (Notion + Prometheus)

```python
# polling_service/handler.py (Scheduled Lambda)
import boto3
from notion_client import Client as NotionClient
import requests

def poll_notion(event, context):
    """Poll Notion databases for changes (every 15 min via EventBridge)"""
    
    notion = NotionClient(auth=os.environ['NOTION_TOKEN'])
    
    # Query roadmap database
    results = notion.databases.query(
        database_id=os.environ['NOTION_ROADMAP_DB'],
        filter={"property": "Last edited time", "date": {"past_week": {}}}
    )
    
    for page in results['results']:
        # Create normalized event and send to SQS
        normalized = {
            'source': 'notion',
            'event_type': 'page_updated',
            'payload': page,
            'timestamp': page['last_edited_time']
        }
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(normalized))

def poll_prometheus(event, context):
    """Scrape metrics from Prometheus (every 5 min via EventBridge)"""
    
    prometheus_url = os.environ['PROMETHEUS_URL']
    
    metrics = [
        'deployment_success_rate',
        'build_duration_seconds',
        'http_request_duration_seconds',
        'error_rate_5xx'
    ]
    
    for metric in metrics:
        response = requests.get(f"{prometheus_url}/api/v1/query", params={
            'query': metric
        })
        
        for result in response.json()['data']['result']:
            normalized = {
                'source': 'prometheus',
                'event_type': 'metric_sample',
                'payload': {
                    'metric': metric,
                    'value': result['value'][1],
                    'labels': result['metric']
                },
                'timestamp': result['value'][0]
            }
            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(normalized))
```

---

## 6. Unified Data Access Layer

### The Key Pattern: Centralized Query Service

```python
# data_access/unified_client.py
"""
Unified interface for AI agents to query any database.
All agents use this instead of directly connecting to DBs.
"""

class UnifiedDataClient:
    def __init__(self):
        self.aurora = AuroraClient()
        self.clickhouse = ClickHouseClient()
        self.pinecone = PineconeClient()
        self.neo4j = Neo4jClient()
    
    # --- Cross-database queries ---
    
    async def get_developer_profile_complete(self, email: str) -> dict:
        """Get complete developer profile from ALL databases"""
        
        # Aurora: Basic info
        user = await self.aurora.get_user_by_email(email)
        
        # ClickHouse: Activity metrics
        metrics = await self.clickhouse.query('''
            SELECT 
                countIf(event_type = 'commit') as commits_30d,
                countIf(event_type = 'pr_merged') as prs_30d,
                countIf(event_type = 'pr_reviewed') as reviews_30d
            FROM events
            WHERE actor_id = %(email)s AND timestamp >= today() - 30
        ''', {'email': email})
        
        # Neo4j: Relationships
        graph_data = await self.neo4j.run('''
            MATCH (u:User {email: $email})-[:CONTRIBUTES_TO]->(p:Project)
            MATCH (u)-[:HAS_SKILL]->(s:Skill)
            RETURN collect(DISTINCT p.name) as projects, 
                   collect(DISTINCT s.name) as skills
        ''', email=email)
        
        # Pinecone: Embedding (for similarity search later)
        embedding = await self.pinecone.fetch(
            namespace="developer_profiles",
            ids=[user['id']]
        )
        
        return {
            'user': user,
            'metrics': metrics,
            'projects': graph_data['projects'],
            'skills': graph_data['skills'],
            'embedding': embedding
        }
    
    async def get_project_health(self, project_id: str) -> dict:
        """Complete project health from all sources"""
        
        # Aurora: Basic info
        project = await self.aurora.get_project(project_id)
        
        # ClickHouse: DORA metrics
        dora = await self.clickhouse.query('''
            SELECT * FROM dora_daily_metrics
            WHERE project_id = %(id)s AND date >= today() - 30
        ''', {'id': project_id})
        
        # Neo4j: Dependencies and team
        graph = await self.neo4j.run('''
            MATCH (p:Project {id: $id})<-[:DEPENDS_ON]-(d:Project)
            MATCH (u:User)-[:CONTRIBUTES_TO]->(p)
            RETURN collect(DISTINCT d.name) as dependents,
                   collect(DISTINCT u.name) as contributors
        ''', id=project_id)
        
        return {
            'project': project,
            'dora_metrics': dora,
            'dependents': graph['dependents'],
            'team': graph['contributors']
        }
    
    async def find_matching_developers(
        self, 
        requirements: str, 
        embedding: list,
        min_availability: float = 0.3
    ) -> list:
        """RAG: Find developers matching requirements with availability"""
        
        # Pinecone: Semantic search
        matches = await self.pinecone.query(
            namespace="developer_profiles",
            vector=embedding,
            top_k=10,
            include_metadata=True
        )
        
        results = []
        for match in matches:
            email = match['metadata']['email']
            
            # ClickHouse: Check current workload
            workload = await self.clickhouse.query('''
                SELECT count(*) as active_issues
                FROM events
                WHERE actor_id = %(email)s 
                  AND event_type = 'issue_assigned'
                  AND timestamp >= today() - 14
            ''', {'email': email})
            
            # Simple availability calculation
            max_capacity = 10  # issues
            availability = max(0, (max_capacity - workload['active_issues']) / max_capacity)
            
            if availability >= min_availability:
                results.append({
                    'email': email,
                    'name': match['metadata']['name'],
                    'match_score': match['score'],
                    'availability': availability,
                    'skills': match['metadata'].get('skills', [])
                })
        
        return sorted(results, key=lambda x: x['match_score'], reverse=True)[:5]
```

### Using in AI Agents

```python
# agents/rag_agent.py
from data_access.unified_client import UnifiedDataClient

client = UnifiedDataClient()

@tool
async def find_best_developers(requirements: str, top_k: int = 5):
    """Find developers matching project requirements"""
    
    # Generate embedding for requirements
    embedding = await openai.embeddings.create(
        model="text-embedding-3-small",
        input=requirements
    )
    
    # Use unified client (queries Pinecone + ClickHouse)
    matches = await client.find_matching_developers(
        requirements=requirements,
        embedding=embedding.data[0].embedding,
        min_availability=0.3
    )
    
    return matches
```

---

## 7. AWS Infrastructure Summary

| Component | AWS Service | Purpose | Cost Estimate |
|-----------|-------------|---------|---------------|
| **Webhook Receiver** | API Gateway + Lambda | Receive webhooks | ~$5/mo |
| **Event Queue** | SQS | Buffer events | ~$1/mo |
| **Event Processing** | Lambda | Process & route events | ~$10/mo |
| **Polling Scheduler** | EventBridge | Trigger Notion/Prometheus polls | ~$1/mo |
| **Primary DB** | Aurora PostgreSQL Serverless v2 | Entities & relationships | ~$30-50/mo |
| **Time-Series DB** | ClickHouse Cloud (via Marketplace) | Events & metrics | ~$67/mo |
| **Vector DB** | Pinecone | Embeddings & search | Free tier |
| **Graph DB** | Neo4j Aura | Relationship queries | Free tier |
| **Secrets** | Secrets Manager | API keys & credentials | ~$2/mo |
| **Logs** | CloudWatch | Monitoring & debugging | ~$5/mo |

**Estimated Total: ~$120-140/month** (production-ready setup)

For hackathon: Use free tiers where available → **~$70/month**

---

## 8. Setup Checklist

### Day 1: Database Setup

- [ ] Create Aurora PostgreSQL cluster (AWS Console)
- [ ] Create ClickHouse Cloud account + Basic tier instance
- [ ] Create Pinecone account + index `engineering-intelligence`
- [ ] Create Neo4j Aura account + free instance
- [ ] Store all credentials in AWS Secrets Manager

### Day 1: Ingestion Setup

- [ ] Deploy API Gateway with `/webhooks/github` and `/webhooks/jira` routes
- [ ] Deploy Lambda webhook receivers
- [ ] Create SQS queue for events
- [ ] Deploy Lambda event processor
- [ ] Set up EventBridge rules for Notion/Prometheus polling

### Day 2: Schema & Data Loading

- [ ] Run Aurora schema migrations
- [ ] Create ClickHouse tables and materialized views
- [ ] Create Pinecone namespaces
- [ ] Create Neo4j node/relationship schema
- [ ] Load sample data for demo

### Day 2-3: Unified Client & Agents

- [ ] Implement UnifiedDataClient
- [ ] Connect AI agents to unified client
- [ ] Test cross-database queries

---

## 9. Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW BY SOURCE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  GITHUB                                                                 │
│  ├── Commits, PRs, Reviews ──────────────────► ClickHouse (events)     │
│  ├── Contributor stats ──────────────────────► Aurora (user metrics)   │
│  ├── Developer activity summaries ───────────► Pinecone (embeddings)   │
│  └── Contribution relationships ─────────────► Neo4j (graphs)          │
│                                                                         │
│  JIRA                                                                   │
│  ├── Issue events, Sprint data ──────────────► ClickHouse (events)     │
│  ├── Project/Epic metadata ──────────────────► Aurora (projects)       │
│  ├── Epic descriptions ──────────────────────► Pinecone (docs)         │
│  └── User-Project assignments ───────────────► Neo4j (graphs)          │
│                                                                         │
│  NOTION                                                                 │
│  ├── Page updates ───────────────────────────► ClickHouse (events)     │
│  ├── Roadmap items ──────────────────────────► Aurora (projects)       │
│  ├── Documentation ──────────────────────────► Pinecone (docs)         │
│  └── Project dependencies ───────────────────► Neo4j (graphs)          │
│                                                                         │
│  PROMETHEUS                                                             │
│  ├── All metrics ────────────────────────────► ClickHouse (metrics)    │
│  └── (no other databases needed)                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*This cloud architecture is designed for hackathon speed while being production-scalable. All databases are managed services with free or low-cost tiers.*
