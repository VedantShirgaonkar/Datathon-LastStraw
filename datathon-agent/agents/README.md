# Engineering Intelligence Agent System

This module implements the multi-agent system for the Engineering Intelligence Platform, utilizing LangGraph and Featherless.ai.

## Architecture

- **Supervisor Agent:** `agents/supervisor.py` - Orchestrates the workflow using LangGraph.
- **Tools:**
  - `agents/tools/postgres_tools.py` - Entity data (Users, Teams, Projects)
  - `agents/tools/clickhouse_tools.py` - Event data & DORA metrics
  - `agents/tools/neo4j_tools.py` - Collaboration graphs
  - `agents/tools/vector_tools.py` - Semantic search & skill matching
- **Infrastructure:**
  - `agents/utils/db_clients.py` - Singleton database clients
  - `agents/utils/config.py` - Typed configuration loading
  - `agents/utils/logger.py` - Structural logging with phase tracking

## Prerequisites

Ensure your `.env` file is configured with:
- Database credentials (Postgres, ClickHouse, Neo4j)
- Featherless API key and model (`Qwen/Qwen2.5-72B-Instruct` recommended)

## Usage

### Interactive Mode
Run the agent in interactive CLI mode to chat with your data:

```bash
python3 -m agents.main
```

### Single Query
Run a specific query directly from the command line:

```bash
python3 -m agents.main -q "What are the DORA metrics for API Gateway?"
```

### Running Tests
Verify connections and tools:

```bash
# Test Database Connections
python3 -m agents.tests.test_connections

# Test Individual Tools
python3 -m agents.tests.test_tools

# Test End-to-End Agent
python3 -m agents.tests.test_agent
```

## Supported Queries

- **Developer Info:** "Who is [Name]?", "Find developers with [Skill] expertise"
- **Project Status:** "What is the status of [Project]?", "List high priority projects"
- **Metrics:** "What are the DORA metrics for [Project]?", "Show deployment frequency"
- **Collaboration:** "Who collaborates with [Name]?", "Show knowledge experts for [Topic]"
