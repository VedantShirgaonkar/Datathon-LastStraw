# Data Extraction API

A FastAPI backend that receives webhook events from Jira and GitHub, and queries Notion databases.

## Overview

This backend receives **webhook events** from Jira and GitHub (push model), and uses **REST API** for Notion (pull model). All data is returned as raw JSON.

### Supported Sources

| Source | Type | Description |
|--------|------|-------------|
| **Jira Cloud** | Webhook | Receives issue events pushed from Jira |
| **GitHub** | Webhook | Receives PR, commit, issue events from GitHub |
| **Notion** | REST API | Queries databases and pages |

## Quick Start

### 1. Install Dependencies

```bash
cd data-extraction-api
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

### 3. Run the Server

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Webhook Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/jira` | POST | Receives Jira webhook events |
| `/webhooks/github` | POST | Receives GitHub webhook events |

### Notion Endpoints

```bash
# Query database
curl "http://localhost:8000/notion/database/query?page_size=25"

# Get single page
curl http://localhost:8000/notion/page/{page_id}
```

## Webhook Setup

### GitHub Webhook

1. Go to your repo → **Settings** → **Webhooks** → **Add webhook**
2. **Payload URL**: `https://your-server.com/webhooks/github`
3. **Content type**: `application/json`
4. **Secret**: Your `GITHUB_WEBHOOK_SECRET`
5. Select events to receive (push, pull requests, etc.)

### Jira Webhook

1. Go to **Jira Settings** → **System** → **Webhooks**
2. Click **Create a webhook**
3. **URL**: `https://your-server.com/webhooks/jira`
4. Select events (issue created, updated, etc.)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_TOKEN` | ✅ | Notion integration token |
| `NOTION_DATABASE_ID` | ✅ | Notion database ID |
| `GITHUB_WEBHOOK_SECRET` | Optional | For signature verification |
| `JIRA_WEBHOOK_SECRET` | Optional | For signature verification |

## Webhook Response Format

```json
{
  "source": "github",
  "delivery_id": "abc123",
  "event_type": "push",
  "payload": { ... raw webhook payload ... }
}
```

## Features

- ⚡ **Async HTTP** - Using `httpx` for Notion queries
- 🔐 **HMAC Verification** - Secure webhook signature validation
- 📖 **Auto Docs** - Swagger UI at `/docs`
- ✅ **Validation** - Environment variables validated on startup

## Project Structure

```
data-extraction-api/
├── main.py
├── clients/
│   └── notion.py           # Notion REST client
├── routers/
│   ├── health.py
│   ├── notion.py
│   └── webhooks/
│       ├── jira.py         # Jira webhook receiver
│       └── github.py       # GitHub webhook receiver
├── schemas/
│   └── responses.py
├── utils/
│   ├── config.py
│   └── exceptions.py
└── requirements.txt
```
