# Database Layer Architecture Guide

> **For: The Database Layer Owner**
> 
> A conceptual guide with zero code — focused on understanding the architecture

---

## The Big Picture

Your responsibility is the **data storage and retrieval layer** that sits between Kafka (events coming in) and the downstream services (AI agents, dashboards, automations).

```
API Gateway → Kafka → [YOUR LAYER] → AI Agents / Dashboards
     │                    │
     │                    ├── Routing Agent (decides where data goes)
     │                    ├── Aurora PostgreSQL (entities)
     │                    ├── ClickHouse (events/metrics)
     │                    ├── Pinecone (embeddings)
     │                    └── Neo4j Aura (relationships)
     │
     └── Webhooks from GitHub, Jira, Notion, Prometheus
```

---

## 1. Why Kafka? What Does It Actually Do?

### The Problem Without Kafka

Imagine webhooks coming directly to your databases:
- If one database is slow, the webhook times out
- If a database crashes, events are lost forever
- If you add a new database later, you need to modify the webhook handler
- If 1000 events come in 1 second, databases get overwhelmed

### What Kafka Solves

Think of Kafka as a **super-reliable post office that never loses mail**:

| Without Kafka | With Kafka |
|---------------|------------|
| Events go directly to DBs | Events first go to Kafka, then to DBs |
| Lose events if DB is down | Kafka holds events until DB recovers |
| Hard to add new consumers | Easy to add new consumers anytime |
| One event → one destination | One event → many destinations (fan-out) |

### Kafka's Three Key Responsibilities

1. **Durable Buffer**
   - Events are stored on disk, not just in memory
   - If your database crashes, events wait in Kafka
   - Events can be replayed if something goes wrong

2. **Fan-Out Distribution**
   - Single event from GitHub can go to 4+ databases simultaneously
   - Each database consumer is independent
   - Adding a new consumer doesn't affect existing ones

3. **Guaranteed Ordering**
   - Events from the same source stay in order
   - Commit A → Commit B → Commit C always processed in sequence
   - Critical for maintaining data consistency

### Kafka Terminology (Simple Explanations)

| Term | What It Means |
|------|--------------|
| **Topic** | A named channel for events (like a mailbox) |
| **Producer** | Something that sends events to Kafka (your teammate's API Gateway) |
| **Consumer** | Something that reads events from Kafka (your routing agent) |
| **Partition** | A way to split a topic for parallelism |
| **Consumer Group** | Multiple consumers sharing the load |

---

## 2. The Routing Agent's Dual Responsibility

The "agent" sitting between Kafka and databases has TWO jobs:

### Responsibility 1: Route to Correct Databases

When an event arrives (e.g., "GitHub commit happened"), the agent decides:

```
INCOMING: GitHub commit event
         │
         ├──► Aurora PostgreSQL: Update developer activity stats
         │
         ├──► ClickHouse: Store raw event for analytics
         │
         ├──► Pinecone: Update developer's skill embedding
         │
         └──► Neo4j: Create CONTRIBUTED_TO relationship
```

**The routing logic is based on event type:**

| Event Type | Aurora | ClickHouse | Pinecone | Neo4j |
|------------|--------|------------|----------|-------|
| GitHub Commit | ✓ Update user stats | ✓ Store event | Maybe | ✓ Contribution link |
| GitHub PR Merged | ✓ Update project | ✓ Store + aggregate | ✓ Update profile | ✓ Review relationship |
| Jira Issue Updated | ✓ Sync project | ✓ Store event | Maybe | ✓ Assignment link |
| Jira Sprint Closed | ✓ Update velocity | ✓ Store + aggregate | ✗ | ✗ |
| Prometheus Metric | ✗ | ✓ Store metric | ✗ | ✗ |

### Responsibility 2: Route Back to Source Systems (Upstream)

Sometimes, an event needs to trigger an UPDATE in a source system:

**Example: GitHub Commit → Jira Update**
```
1. Developer commits code with message "PROJ-123 fixed login bug"
2. Your agent detects the Jira issue key "PROJ-123" in the commit
3. Agent makes an API call to Jira to:
   - Add a comment with the commit details
   - Optionally transition the issue (e.g., to "In Review")
```

**Example: Jira Status Change → Slack Notification**
```
1. Issue PROJ-456 moves to "Blocked" status
2. Agent detects this is a high-priority issue
3. Agent sends notification to project's Slack channel
```

This is called **bi-directional sync** or **event-driven automation**.

---

## 3. Which Databases to Use (AWS vs External)

With your $100 AWS credits, here's the optimal split:

### Inside AWS (Use Credits)

| Database | AWS Service | Why AWS? | Estimated Cost |
|----------|-------------|----------|----------------|
| **Primary DB** | Aurora PostgreSQL Serverless v2 | Fully managed, auto-scales, native AWS | ~$30-50/month |
| **Event Streaming** | Amazon MSK Serverless (Kafka) | Managed Kafka, pay per use | ~$20-30/month |

### Outside AWS (Free Tiers / Better Options)

| Database | Service | Why External? | Cost |
|----------|---------|---------------|------|
| **Time-Series** | ClickHouse Cloud | 100x faster than any AWS analytics DB | $67/mo (or use trial) |
| **Vector DB** | Pinecone | Purpose-built, serverless, free tier | **FREE** (100K vectors) |
| **Graph DB** | Neo4j Aura | Better than AWS Neptune for your use case | **FREE** (50K nodes) |

### Why Not Use Everything on AWS?

Honest assessment:

| AWS Option | Why We're NOT Using It |
|------------|------------------------|
| **AWS Neptune** (Graph) | More expensive than Neo4j Aura free tier, learning curve is steeper with Gremlin query language |
| **AWS Timestream** (Time-Series) | Slower than ClickHouse for OLAP queries, proprietary query language |
| **AWS OpenSearch** (Vector) | Overkill for your needs, Pinecone is simpler and free |

---

## 4. Understanding Each Database's Role

### Aurora PostgreSQL: The "Source of Truth"

**What it stores:**
- Users and their identities across systems
- Projects and their metadata
- Teams and organizational structure
- Identity mappings (linking GitHub username to Jira username to Slack ID)

**Why Aurora over regular PostgreSQL:**
- Auto-scales based on demand (no manual sizing)
- Serverless v2 means you pay only when queries run
- Built-in backups and point-in-time recovery
- High availability across AWS zones

**When other services query it:**
- "Who is the user with GitHub username 'johndoe'?"
- "What projects does Team Alpha own?"
- "What's the hourly rate for this developer?"

---

### ClickHouse Cloud: The "Event Brain"

**What it stores:**
- Every single event (commits, PRs, issues, metrics)
- Pre-computed aggregations (daily DORA metrics, weekly velocity)
- Historical trends and patterns

**Why ClickHouse over AWS alternatives:**
- Processes billions of rows in milliseconds
- Columnar storage = 10x compression
- SQL syntax (familiar, not proprietary)
- Real-time materialized views (auto-aggregate as data arrives)

**When other services query it:**
- "What's the deployment frequency for Project X this month?"
- "Show me the trend of PR review time over the last quarter"
- "Which developer has the most commits this sprint?"

---

### Pinecone: The "Semantic Memory"

**What it stores:**
- Developer profiles as numerical vectors (embeddings)
- Project documentation chunks as vectors
- Skills and expertise representations

**Why external Pinecone:**
- Purpose-built for similarity search
- Free tier is generous (100K vectors)
- Simple API, no infrastructure to manage
- Integrates directly with OpenAI embeddings

**When other services query it:**
- "Find developers similar to this project requirement"
- "Which documentation is most relevant to this question?"
- "Match me with developers who have worked on similar problems"

---

### Neo4j Aura: The "Relationship Memory"

**What it stores:**
- Who works on what project
- Which projects depend on which other projects
- Team hierarchies and reporting structures
- Skill graphs (who knows what)

**Why external Neo4j Aura:**
- Free tier is sufficient (50K nodes, 175K relationships)
- Cypher query language is intuitive
- Built-in visualization tools
- Better for complex relationship queries than SQL

**When other services query it:**
- "If Project X is delayed, what other projects are affected?"
- "Find all developers within 2 hops of the Platform team"
- "What's the dependency chain for this release?"

---

## 5. AWS Setup Guide for Beginners

Since you haven't used AWS before, here's a step-by-step mental model:

### Step 0: Create AWS Account

1. Go to aws.amazon.com
2. Create account with your email
3. Add credit card (won't be charged with credits)
4. Apply your $100 educational/promo credits

### Step 1: Understanding AWS Structure

```
AWS Account
    │
    └── Region (e.g., us-east-1)
            │
            ├── VPC (Virtual Private Cloud) - your isolated network
            │       │
            │       ├── Subnet (public/private)
            │       └── Security Groups (firewall rules)
            │
            ├── Aurora PostgreSQL (database)
            ├── MSK Serverless (Kafka)
            ├── Lambda (serverless functions)
            └── Secrets Manager (store credentials)
```

### Step 2: Set Up Aurora PostgreSQL Serverless

**Where:** AWS Console → RDS → Create Database

**Key Choices:**
- Engine: Aurora PostgreSQL Compatible
- Capacity type: Serverless v2
- Min capacity: 0.5 ACU (lowest cost)
- Max capacity: 4 ACU (handles spikes)
- Enable public access: NO (security)
- Create in a VPC with private subnets

**What you'll get:**
- An endpoint URL to connect to
- Auto-scaling based on queries
- Automatic backups

### Step 3: Set Up MSK Serverless (Kafka)

**Where:** AWS Console → Amazon MSK → Create Cluster

**Key Choices:**
- Cluster type: Serverless (NOT Provisioned)
- VPC: Same VPC as Aurora
- Authentication: IAM authentication

**What you'll get:**
- A bootstrap server URL
- Topics you create for different event types
- Pay only for what you use

### Step 4: Set Up Secrets Manager

**Where:** AWS Console → Secrets Manager → Store New Secret

**What to store:**
- Aurora database credentials
- ClickHouse Cloud credentials
- Pinecone API key
- Neo4j Aura credentials
- GitHub/Jira API tokens

**Why:** Never hardcode credentials. Services retrieve them securely at runtime.

---

## 6. How the Databases Connect

### The Connection Pattern

```
                    ┌─────────────────────────────────────────┐
                    │               KAFKA (MSK)               │
                    │  Topics: github-events, jira-events,   │
                    │          notion-events, prom-metrics   │
                    └─────────────────────┬───────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │          ROUTING AGENT (Lambda)         │
                    │  Reads from Kafka, decides destinations │
                    └───┬─────────┬─────────┬─────────┬───────┘
                        │         │         │         │
           ┌────────────┘         │         │         └────────────┐
           ▼                      ▼         ▼                      ▼
    ┌─────────────┐      ┌─────────────┐ ┌─────────────┐   ┌─────────────┐
    │   Aurora    │      │ ClickHouse  │ │  Pinecone   │   │  Neo4j      │
    │ PostgreSQL  │      │    Cloud    │ │             │   │   Aura      │
    └──────┬──────┘      └──────┬──────┘ └──────┬──────┘   └──────┬──────┘
           │                    │               │                  │
           └────────────────────┴───────────────┴──────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │      UNIFIED DATA ACCESS LAYER          │
                    │  (Lambda function your agents call)     │
                    └─────────────────────────────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │           AI AGENTS / DASHBOARDS        │
                    └─────────────────────────────────────────┘
```

### Why This Architecture Works

1. **Decoupling**: Kafka separates event producers from consumers
2. **Resilience**: Any database can fail; others continue working
3. **Flexibility**: Add new databases without changing upstream
4. **Efficiency**: Each database does what it's best at

---

## 7. Cost Breakdown ($100 Budget)

### Monthly Estimates

| Service | Provider | Cost | Notes |
|---------|----------|------|-------|
| Aurora PostgreSQL Serverless v2 | AWS | ~$30-40 | Min 0.5 ACU, scales to 4 |
| MSK Serverless (Kafka) | AWS | ~$15-25 | Pay per data transferred |
| Secrets Manager | AWS | ~$2 | 4-5 secrets |
| Lambda (Routing Agent) | AWS | ~$5 | Generous free tier |
| ClickHouse Cloud | External | $0-67 | Use trial credits or Basic tier |
| Pinecone | External | $0 | Free tier (100K vectors) |
| Neo4j Aura | External | $0 | Free tier (50K nodes) |

**Total AWS Spend: ~$50-70/month** (within credits)
**Total External: $0-67/month** (free tiers available)

### Staying Within Budget

For a 72-hour hackathon:
- Aurora + MSK for 3 days ≈ $3-5
- ClickHouse trial ≈ $0 (trial credits)
- Pinecone + Neo4j ≈ $0 (free tiers)

**You can easily do this hackathon for under $10 of actual spend.**

---

## 8. What You Need to Set Up

### Your Setup Checklist

**Day 1: External Services (Free)**
- [ ] Create Pinecone account at pinecone.io
- [ ] Create index named `engineering-intelligence`
- [ ] Create Neo4j Aura account at console.neo4j.io
- [ ] Create free-tier instance, save credentials
- [ ] Create ClickHouse Cloud account at clickhouse.cloud
- [ ] Start trial or Basic tier on AWS region

**Day 1: AWS Setup**
- [ ] Log into AWS Console
- [ ] Choose region: us-east-1 (most services available)
- [ ] Create Aurora PostgreSQL Serverless v2 cluster
- [ ] Create MSK Serverless cluster in same VPC
- [ ] Store all credentials in Secrets Manager

**Day 2: Schema Design**
- [ ] Design Aurora tables (users, projects, teams, identity_mappings)
- [ ] Design ClickHouse tables (events with time partitioning)
- [ ] Design Pinecone namespaces (developer_profiles, project_docs)
- [ ] Design Neo4j node/relationship schema

**Day 2-3: Integration**
- [ ] Create Lambda function for routing agent
- [ ] Connect routing agent to Kafka topics
- [ ] Test write path to each database
- [ ] Coordinate with teammate on API Gateway connection

---

## 9. Questions You Should Ask Your Teammate

Since your teammate is building the API Gateway → Kafka portion:

1. **What Kafka topics will you create?**
   - github-events, jira-events, notion-events, prometheus-metrics?
   - Or one combined events topic?

2. **What format will events be in?**
   - Raw webhook payloads?
   - Normalized structure?
   - JSON schema?

3. **How will you handle authentication to Kafka?**
   - IAM authentication?
   - SASL/SCRAM?

4. **Where will the Kafka cluster live?**
   - Same VPC as my databases?
   - Need VPC peering?

5. **What's the expected event volume?**
   - Helps size Aurora and ClickHouse

---

## 10. Summary: Your Responsibilities

| Your Job | What It Means |
|----------|---------------|
| **Set up Aurora PostgreSQL** | Create cluster, define schema, manage migrations |
| **Set up ClickHouse Cloud** | Create tables, materialized views for aggregations |
| **Set up Pinecone** | Create index, define namespaces |
| **Set up Neo4j Aura** | Create instance, define node/relationship schema |
| **Build Routing Agent** | Lambda that reads Kafka → writes to DBs |
| **Build Upstream Router** | Logic to call Jira/Slack APIs when needed |
| **Build Data Access Layer** | Unified interface for AI agents to query any DB |

---

*This document contains zero code intentionally. It's designed to help you understand the architecture before implementing it.*
