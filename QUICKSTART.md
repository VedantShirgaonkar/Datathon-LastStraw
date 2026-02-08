# 🚀 Quick Start - Production Server

## Run This ONE File

```bash
.\.venv\Scripts\python.exe server.py
```

**That's it!** ✅

## What It Does

- Runs on **port 8000**
- Receives webhooks from GitHub, Jira, Notion
- Processes with LangGraph agent
- **ALWAYS logs** to ClickHouse, Neo4j, pgvector
- **Intelligently syncs** Jira/GitHub/Notion

## Endpoints

- `POST /webhooks/github` - GitHub webhooks
- `POST /webhooks/jira` - Jira webhooks  
- `POST /webhooks/notion` - Notion webhooks
- `POST /agent/process` - Direct agent testing
- `GET /health` - Health check

## Test

```bash
.\.venv\Scripts\python.exe test_webhooks.py
```

## Deploy

Upload `server.py` + dependencies to any cloud platform!
