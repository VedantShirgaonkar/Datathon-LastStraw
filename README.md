# AI-Driven Enterprise Delivery & Workforce Intelligence Platform

Hackathon project implementing multi-database architecture with AI agents for engineering intelligence.

## Overview

This platform provides:
- **Real-time Analytics**: DORA metrics, developer activity, sprint predictions
- **AI Agents**: Intelligent task assignment, skill-based recommendations
- **Multi-Database Architecture**: Neo4j (graph) + ClickHouse (time-series) + PostgreSQL (entities) + Pinecone (vectors)
- **Event-Driven**: Kafka streaming with LangGraph-powered agent

## Architecture

```
┌──────────────────┐
│  Apache Kafka    │  ← Event Stream (GitHub, Jira, Notion)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────┐
│  Database Agent (LangGraph)      │  ← Featherless AI (Qwen3-32B)
│  • Event Classification          │
│  • Tool Selection                │
│  • Pydantic Validation           │
│  • Multi-DB Operations           │
└────────┬─────────────────────────┘
         │
         ├─────────┬─────────┬─────────┐
         ▼         ▼         ▼         ▼
    ┌────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐
    │ Neo4j  │ │ ClickH. │ │Postgres│ │Pinecone │
    │ Graph  │ │TimeSerie│ │Entities│ │ Vectors │
    └────────┘ └─────────┘ └────────┘ └─────────┘
```

## Project Structure

```
DataThon/
├── agent/                          # AI Agent (LangGraph + Pydantic)
│   ├── agent.py                    # LangGraph workflow (4 nodes)
│   ├── kafka_consumer.py           # Event processor
│   ├── config.py                   # Configuration
│   ├── schemas/
│   │   └── tool_schemas.py         # Pydantic I/O schemas
│   ├── tools/
│   │   ├── neo4j_tools.py          # Graph database tools (5)
│   │   └── clickhouse_tools.py     # Time-series tools (5)
│   ├── quick_start.py              # Quick start script
│   ├── test_agent.py               # Test suite
│   └── README.md                   # Agent documentation
│
├── neo4j/                          # Neo4j Graph Database
│   ├── neo4j_client.py             # Client wrapper
│   ├── neo4j_schema.py             # Schema setup (9 constraints, 19 indexes)
│   ├── neo4j_connection_test.py    # Connection test
│   └── NEO4J_SETUP_GUIDE.md
│
├── clickhouse/                     # ClickHouse Time-Series DB
│   ├── clickhouse_client.py        # Client wrapper
│   ├── clickhouse_schema.py        # Schema + DORA metrics view
│   ├── clickhouse_connection_test.py
│   ├── query_data.py               # Analytics queries
│   └── CLICKHOUSE_SETUP_GUIDE.md
│
├── config.py                       # Centralized DB config
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment template
└── README.md                       # This file
```

## Quick Start

### 1. Clone and Setup

```bash
cd c:\PF\Projects\DataThon

# Create virtual environment with UV
uv venv
.venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in credentials:

```env
# Featherless AI (Required for agent)
FEATHERLESS_API_KEY=your_api_key_here
FEATHERLESS_MODEL=Qwen/Qwen3-32B

# Neo4j Aura (Required)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password_here

# ClickHouse Cloud (Required)
CLICKHOUSE_HOST=xxxxx.aws.clickhouse.cloud
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=your_password_here

# Kafka (Required for agent)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=engineering-events
```

### 3. Setup Databases

#### Neo4j Aura (Graph Database)

```bash
# Test connection
python neo4j/neo4j_connection_test.py

# Setup schema (9 constraints, 19 indexes)
python neo4j/neo4j_schema.py
```

See [neo4j/NEO4J_SETUP_GUIDE.md](neo4j/NEO4J_SETUP_GUIDE.md) for details.

#### ClickHouse Cloud (Time-Series)

```bash
# Test connection
python clickhouse/clickhouse_connection_test.py

# Setup schema + DORA metrics view
python clickhouse/clickhouse_schema.py

# Insert sample data (100 events)
python -c "from clickhouse.clickhouse_schema import insert_sample_data; insert_sample_data()"

# Query sample data
python clickhouse/query_data.py
```

See [clickhouse/CLICKHOUSE_SETUP_GUIDE.md](clickhouse/CLICKHOUSE_SETUP_GUIDE.md) for details.

### 4. Start Agent

```bash
# Quick start with validation
python agent/quick_start.py

# Or start directly
python agent/kafka_consumer.py
```

See [agent/README.md](agent/README.md) for full agent documentation.

## Database Schema

### Neo4j (Graph)

**Nodes:**
- Developer (email, name, team_id)
- Team (id, name)
- Project (id, name, key)
- Skill (name)
- Sprint (id, start_date, end_date)
- Feature (id, name, description)

**Relationships:**
- BELONGS_TO (Developer → Team)
- HAS_SKILL (Developer → Skill) [proficiency]
- CONTRIBUTES_TO (Developer → Project) [commits, prs, reviews]
- DEPENDS_ON (Project → Project) [type]
- ASSIGNED_TO (Feature → Developer)
- IN_SPRINT (Feature → Sprint)

**Indexes:** 19 indexes for fast queries

### ClickHouse (Time-Series)

**events Table:**
```sql
CREATE TABLE events (
    event_id String,
    timestamp DateTime,
    event_type String,
    project_id String,
    developer_email String,
    metadata String,  -- JSON
    date Date
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (project_id, developer_email, timestamp);
```

**dora_daily_metrics Materialized View:**
- deployment_frequency (deployments per day)
- avg_lead_time_hours (PR creation to merge)
- prs_merged
- story_points_completed

## Agent Tools

### Neo4j Tools (5)
- `create_developer_node` - Create developer node
- `add_skill_relationship` - Add skill to developer
- `add_contribution_relationship` - Record project contribution
- `create_project_dependency` - Link dependent projects
- `find_available_developers` - Query devs with skill + availability

### ClickHouse Tools (5)
- `insert_commit_event` - Record git commit
- `insert_pr_event` - Record PR (for DORA metrics)
- `insert_jira_event` - Record Jira issue event
- `get_developer_activity_summary` - Get dev productivity
- `get_project_dora_metrics` - Get DORA metrics

### Coming Soon
- PostgreSQL + pgvector tools (10)
- Pinecone vector search tools (5)
- Notification tools (Slack, Email) (3)
- Jira integration tools (4)

## Testing

### Test Databases

```bash
# Neo4j
python neo4j/neo4j_connection_test.py

# ClickHouse
python clickhouse/clickhouse_connection_test.py
python clickhouse/query_data.py
```

### Test Agent

```bash
python agent/test_agent.py
```

Tests:
- ✅ Event classification with Featherless AI
- ✅ Tool selection and parameter extraction
- ✅ Pydantic validation
- ✅ Database operations
- ✅ LangGraph workflow

## Event Schemas

The agent processes events from Kafka in this format:

```json
{
  "source": "github|jira|notion|prometheus|ai_agent",
  "event_type": "commit_pushed|pr_merged|issue_created|...",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "project_id": "proj-api",
    "developer": {
      "email": "alice@company.com",
      "name": "Alice Johnson"
    },
    "...": "event-specific data"
  }
}
```

See [agent/README.md](agent/README.md) for detailed event schemas.

## Configuration

Centralized configuration in `config.py`:

```python
from config import DatabaseConfig

# Access all database configs
config = DatabaseConfig()

print(config.neo4j.uri)          # neo4j+s://xxxxx.databases.neo4j.io
print(config.clickhouse.host)    # xxxxx.aws.clickhouse.cloud
print(config.postgres.host)      # (future)
print(config.pinecone.api_key)   # (future)
```

Agent configuration in `agent/config.py`:

```python
from agent.config import get_config

config = get_config()
print(config.featherless_model)     # Qwen/Qwen3-32B
print(config.max_tool_retries)      # 3
```

## Development

### Adding Database Clients

1. Create `{db_name}/{db_name}_client.py`
2. Add config dataclass to `config.py`
3. Create schema setup script
4. Add connection test
5. Update documentation

### Adding Agent Tools

1. Define Pydantic schemas in `agent/schemas/tool_schemas.py`
2. Implement tool function in `agent/tools/{db_name}_tools.py`
3. Wrap with `StructuredTool.from_function()`
4. Register in `agent/tools/__init__.py`
5. Test with `agent/test_agent.py`

See [agent/README.md](agent/README.md#adding-new-tools) for details.

## Features Planned

### Phase 1: Database Layer (Current)
- [x] Neo4j Aura setup (9 constraints, 19 indexes)
- [x] ClickHouse Cloud setup (events + DORA metrics)
- [x] LangGraph agent with 10 tools
- [x] Kafka event processing
- [x] Pydantic validation
- [ ] PostgreSQL RDS + pgvector
- [ ] Pinecone vector database

### Phase 2: Agent Enhancements
- [ ] PostgreSQL tools (10)
- [ ] Pinecone tools (5)
- [ ] Notification tools (3)
- [ ] Jira tools (4)
- [ ] Tool retry logic
- [ ] Async tool execution
- [ ] Circuit breakers

### Phase 3: API Layer (Teammate)
- [ ] FastAPI REST API
- [ ] GraphQL endpoint
- [ ] WebSocket for real-time
- [ ] Authentication/Authorization

### Phase 4: GenAI Features
- [ ] Voice agents (speech-to-text)
- [ ] AI sprint planning
- [ ] Smart task assignment
- [ ] Skill gap analysis
- [ ] Auto code review
- [ ] Sentiment analysis
- [ ] Predictive alerts

## Tech Stack

**Databases:**
- Neo4j Aura (Graph) - v5.27-enterprise
- ClickHouse Cloud (Time-Series) - v25.8.1
- PostgreSQL RDS (Entities) - Planned
- Pinecone (Vectors) - Planned

**AI/ML:**
- Featherless AI (LLM) - Qwen3-32B
- LangChain (Framework) - v0.3+
- LangGraph (Orchestration) - v0.2+
- Pinecone (Embeddings) - multilingual-e5-large

**Event Streaming:**
- Apache Kafka - Event bus
- Kafka-Python - Consumer

**Python:**
- Python 3.11+
- UV (Package manager)
- Pydantic v2 (Validation)
- pydantic-settings (Config)

## Team

- **Database Layer**: You (Neo4j + ClickHouse + Agent)
- **API Gateway**: Teammate (FastAPI + Kafka producer)

## License

Internal hackathon project

## Support

For issues or questions:
1. Check database setup guides in respective folders
2. Review agent documentation in `agent/README.md`
3. Run test scripts to validate setup
4. Check `.env` configuration

---

**Status**: Phase 1 (Database Layer) - In Progress
- ✅ Neo4j Aura operational
- ✅ ClickHouse Cloud operational
- ✅ Agent with 10 tools implemented
- 🔄 PostgreSQL + Pinecone pending
- 🔄 Full tool suite (42 tools total)
