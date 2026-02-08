# Deployment Guide — Engineering Intelligence Platform

> How to deploy the FastAPI backend so a frontend can consume it.

---

## Table of Contents

1. [Deployment Footprint](#1-deployment-footprint)
2. [HuggingFace Spaces (Recommended for Hackathon)](#2-huggingface-spaces-recommended-for-hackathon)
3. [Alternative Platforms](#3-alternative-platforms)
4. [Environment Variables / Secrets](#4-environment-variables--secrets)
5. [API Quick Reference](#5-api-quick-reference)
6. [Frontend Integration Checklist](#6-frontend-integration-checklist)
7. [Architecture Diagram](#7-architecture-diagram)
8. [Cold Start & Performance Notes](#8-cold-start--performance-notes)

---

## 1. Deployment Footprint

| Component | Size | Notes |
|-----------|------|-------|
| Python packages | ~230 MB | LangGraph, LangChain, pinecone, psycopg2, neo4j, etc. |
| Pinecone inference (hosted) | 0 MB | Embeddings generated via API call — no local model |
| Application code | ~1 MB | 27 Python files, ~7,500 lines |
| **Total disk** | **~250 MB** | Very lightweight for HF Spaces (50 GB limit) |
| **Runtime RAM** | **~500 MB** | No ONNX model in memory — just LangGraph state |
| **GPU required?** | **No** | All LLM + embedding inference is remote via API |

> **Optimisation note:** We switched from `fastembed` (local ONNX) to Pinecone's
> hosted Inference API with `llama-text-embed-v2`. This reduced deployment from
> **~3 GB → ~250 MB** (92% reduction) by eliminating the 2.5 GB ONNX model cache.

### What runs where

```
┌─ Your deployed server (HF Spaces) ──────────────────────────┐
│  FastAPI + Uvicorn                                           │
│  LangGraph supervisor + 3 specialists (orchestration only)   │
│  Pinecone API call — generates 1024-dim query embeddings     │
│  DB clients: psycopg2, neo4j-driver, clickhouse-connect      │
└──────────────┬───────────────────────────────────────────────┘
               │ HTTPS
      ┌────────┼──────────────────────┬────────────────┐
      ▼        ▼                      ▼                ▼
  Featherless  PostgreSQL/Aurora     Pinecone        ClickHouse
  .ai API      + pgvector            Inference API   Cloud
  (LLM calls)  (ap-south-1)          (embeddings)   (ap-south-1)
               Neo4j Aura
```

All heavy computation (LLM + embeddings) is offloaded to remote APIs.
The deployed server is just an **orchestrator** — minimal CPU/RAM needed.

---

## 2. HuggingFace Spaces (Recommended for Hackathon)

### Why it works

| Requirement | HF Spaces Free Tier | Status |
|-------------|---------------------|--------|
| CPU | 2 vCPU | ✅ Sufficient |
| RAM | 16 GB | ✅ ~3 GB needed |
| Disk | 50 GB | ✅ ~3 GB needed |
| GPU | Not needed | ✅ N/A |
| Docker support | Yes (via `Dockerfile`) | ✅ |
| Custom port | 7860 (default) | ✅ |
| Secrets management | HF Secrets UI | ✅ |
| Public URL | `https://<user>-<space>.hf.space` | ✅ |
| CORS | Handled by FastAPI middleware | ✅ |

### Step-by-step deployment

#### 1. Create the HF Space

```bash
# Install the HF CLI (if not already installed)
pip install huggingface_hub

# Login
huggingface-cli login

# Create a new Space (Docker SDK)
huggingface-cli repo create eng-intel-api --type space --space-sdk docker
```

Or via the web UI: https://huggingface.co/new-space → select **Docker** SDK.

#### 2. Set secrets

Go to **Space Settings → Secrets** and add:

| Secret Name | Value |
|-------------|-------|
| `PINECONE_API_KEY` | Your Pinecone API key (get at https://app.pinecone.io/) |
| `FEATHERLESS_API_KEY` | Your Featherless.ai API key |
| `FEATHERLESS_BASE_URL` | `https://api.featherless.ai/v1` |
| `FEATHERLESS_MODEL_PRIMARY` | `Qwen/Qwen2.5-72B-Instruct` |
| `FEATHERLESS_MODEL_CODE` | `deepseek-ai/DeepSeek-Coder-V2-Instruct` |
| `FEATHERLESS_MODEL_FAST` | `Qwen/Qwen2.5-72B-Instruct` |
| `FEATHERLESS_MODEL_ANALYTICS` | `Qwen/Qwen2.5-72B-Instruct` |
| `POSTGRES_HOST` | `engineering-intelligence1.chwmsemq65p7.ap-south-1.rds.amazonaws.com` |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DATABASE` | `engineering_intelligence` |
| `POSTGRES_USER` | *(your value)* |
| `POSTGRES_PASSWORD` | *(your value)* |
| `NEO4J_URI` | `neo4j+s://ca5e560b.databases.neo4j.io` |
| `NEO4J_USERNAME` | *(your value)* |
| `NEO4J_PASSWORD` | *(your value)* |
| `CLICKHOUSE_HOST` | `xgo7i4yevb.ap-south-1.aws.clickhouse.cloud` |
| `CLICKHOUSE_PORT` | `8443` |
| `CLICKHOUSE_PASSWORD` | *(your value)* |

#### 3. Push the code

```bash
cd /Users/rahul/Desktop/Datathon

# Clone the HF Space repo
git clone https://huggingface.co/spaces/<your-username>/eng-intel-api hf-deploy
cd hf-deploy

# Copy the necessary files
cp -r ../agents ./agents
cp -r ../server ./server
cp ../Dockerfile ./Dockerfile

# Commit and push
git add .
git commit -m "Initial deployment"
git push
```

HF Spaces will auto-build the Docker image and start the server.

#### 4. Verify

```bash
# Health check
curl https://<your-username>-eng-intel-api.hf.space/api/health

# Interactive docs
open https://<your-username>-eng-intel-api.hf.space/docs

# Test streaming
curl -N -X POST https://<your-username>-eng-intel-api.hf.space/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Who is Alex Kumar?"}'
```

---

## 3. Alternative Platforms

If HuggingFace Spaces doesn't meet your needs, here are alternatives ranked by ease:

| Platform | Free Tier | Docker | Custom Domain | Cold Start | Best For |
|----------|-----------|--------|---------------|------------|----------|
| **HF Spaces** | ✅ 2 CPU, 16 GB | ✅ | ❌ (subdomain only) | ~60-90s | Hackathon demo |
| **Railway** | $5 credit/mo | ✅ | ✅ | ~10s | Quick production |
| **Render** | Free (750 hrs/mo) | ✅ | ✅ | ~30s (spins down) | Side projects |
| **Fly.io** | Free (3 shared VMs) | ✅ | ✅ | ~5s | Low-latency prod |
| **Google Cloud Run** | Free (2M req/mo) | ✅ | ✅ | ~10s | Scale-to-zero prod |

### Railway (quickest production path)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# Deploy from the project root
cd /Users/rahul/Desktop/Datathon
railway init
railway up
```

Set environment variables via `railway variables set KEY=VALUE`.

### Render

Create a **Web Service** → connect your GitHub repo → set:
- **Build command:** `pip install -r server/requirements.txt`
- **Start command:** `uvicorn server.app:app --host 0.0.0.0 --port $PORT`
- **Docker path:** `./Dockerfile` (or use native Python runtime)

---

## 4. Environment Variables / Secrets

Full list of required environment variables:

```env
# ── Featherless.ai (LLM inference) ──
FEATHERLESS_API_KEY=your_key_here
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL_PRIMARY=Qwen/Qwen2.5-72B-Instruct
FEATHERLESS_MODEL_CODE=deepseek-ai/DeepSeek-Coder-V2-Instruct
FEATHERLESS_MODEL_FAST=Qwen/Qwen2.5-72B-Instruct
FEATHERLESS_MODEL_ANALYTICS=Qwen/Qwen2.5-72B-Instruct

# ── Pinecone (embedding inference) ──
PINECONE_API_KEY=your_pinecone_key_here

# ── PostgreSQL Aurora (+ pgvector) ──
POSTGRES_HOST=engineering-intelligence1.chwmsemq65p7.ap-south-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DATABASE=engineering_intelligence
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# ── Neo4j Aura ──
NEO4J_URI=neo4j+s://ca5e560b.databases.neo4j.io
NEO4J_USERNAME=your_user
NEO4J_PASSWORD=your_password

# ── ClickHouse Cloud ──
CLICKHOUSE_HOST=xgo7i4yevb.ap-south-1.aws.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_DATABASE=default
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=your_password

# ── Optional ──
DEBUG=false
LOG_LEVEL=INFO
PORT=7860
```

---

## 5. API Quick Reference

### `POST /api/chat` — Streaming SSE

```bash
curl -N -X POST http://localhost:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find developers with Python expertise", "thread_id": "optional-id"}'
```

**Response:** Server-Sent Events stream

```
event: stream_start
data: {"event":"stream_start","data":{"query":"Find developers with Python expertise","thread_id":""},...}

event: model_selection
data: {"event":"model_selection","data":{"model":"Qwen 72B","emoji":"🧠","task_type":"deep_analysis",...},...}

event: routing
data: {"event":"routing","data":{"agent":"Insights_Specialist"},...}

event: tool_start
data: {"event":"tool_start","data":{"tool":"find_developer_by_skills","args":{"skills":"Python"}},...}

event: tool_end
data: {"event":"tool_end","data":{"tool":"find_developer_by_skills","result_preview":"5 matches",...},...}

event: response
data: {"event":"response","data":{"content":"Here are developers with Python expertise..."},...}

event: stream_end
data: {"event":"stream_end","data":{"total_tokens":42,"elapsed_s":8.3},...}
```

### `POST /api/chat/sync` — Synchronous JSON

```bash
curl -X POST http://localhost:7860/api/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "How many employees do we have?", "stream": false}'
```

**Response:**
```json
{
  "response": "There are 18 employees across 4 teams...",
  "thread_id": null,
  "model_used": null,
  "task_type": null,
  "elapsed_s": 6.42
}
```

### `POST /api/threads` — Create Thread

```bash
curl -X POST http://localhost:7860/api/threads \
  -H "Content-Type: application/json" \
  -d '{"title": "Sprint Planning Chat"}'
```

### `GET /api/threads` — List Threads

```bash
curl http://localhost:7860/api/threads
```

### `DELETE /api/threads/{id}` — Delete Thread

```bash
curl -X DELETE http://localhost:7860/api/threads/abc123
```

### `GET /api/health` — Health Check

```bash
curl http://localhost:7860/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "uptime_s": 142.3,
  "agent_ready": true,
  "databases": {
    "postgres": "ok",
    "clickhouse": "ok",
    "neo4j": "ok"
  }
}
```

---

## 6. Frontend Integration Checklist

### Consuming SSE in JavaScript / React

```javascript
async function chat(message, threadId, onEvent) {
  const response = await fetch('https://<your-space>.hf.space/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();  // keep incomplete line in buffer

    let eventType = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7);
      } else if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        onEvent(eventType, data);
      }
    }
  }
}

// Usage
chat('Find Python experts', null, (type, data) => {
  switch (type) {
    case 'model_selection':
      setStatusBar(`${data.data.emoji} ${data.data.model}`);
      break;
    case 'routing':
      setStatusBar(`Routing to ${data.data.agent}...`);
      break;
    case 'tool_start':
      addToolToTimeline(data.data.tool, 'running');
      break;
    case 'tool_end':
      updateToolInTimeline(data.data.tool, 'done');
      break;
    case 'response':
      appendMarkdown(data.data.content);
      break;
    case 'error':
      showError(data.data.message);
      break;
  }
});
```

### UI Components to Build

| Component | Consumes Event | What to Show |
|-----------|---------------|-------------|
| **Status Bar** | `model_selection` | Model emoji + name + task type |
| **Routing Badge** | `routing` | "→ Insights_Specialist" chip |
| **Tool Timeline** | `tool_start` / `tool_end` | Animated tool call sequence |
| **Chat Bubble** | `response` | Markdown-rendered answer |
| **Error Toast** | `error` | Red banner with retry button |
| **Stream Progress** | `stream_start` / `stream_end` | Timer + "thinking..." indicator |

---

## 7. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (React)                           │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────────┐    │
│  │  Chat UI │ │Dashboard │ │1:1 Prep    │ │ Anomaly Alerts    │    │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └────────┬──────────┘    │
│       └─────────────┴─────────────┴─────────────────┘               │
│                           │  SSE / REST                             │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│              FastAPI  (HuggingFace Spaces / Railway)                 │
│                                                                     │
│  POST /api/chat  ──▶  SupervisorAgent.stream_query()                │
│  POST /api/chat/sync ──▶  SupervisorAgent.query()                   │
│  CRUD /api/threads  ──▶  ConversationMemory                         │
│  GET  /api/health   ──▶  DB connectivity pings                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  LangGraph Supervisor (Qwen 72B for routing)                │    │
│  │  → DORA_Pro | Resource_Planner | Insights_Specialist        │    │
│  │  → 21 tools: postgres, clickhouse, neo4j, vector, pipelines │    │
│  │  → 5 pipelines: RAG, anomaly, 1:1 prep, NL→SQL, Graph RAG  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  fastembed ONNX (CPU) — query embedding generation                  │
└───────┬──────────────┬──────────────┬──────────────┬────────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐
  │Featherless│  │PostgreSQL │  │ClickHouse│  │  Neo4j Aura  │
  │.ai API   │  │Aurora +   │  │  Cloud   │  │ (Graph DB)   │
  │(LLM)     │  │pgvector   │  │(metrics) │  │              │
  └──────────┘  └───────────┘  └──────────┘  └──────────────┘
```

---

## 8. Cold Start & Performance Notes

### Cold start breakdown (HF Spaces)

| Phase | Time | Notes |
|-------|------|-------|
| Docker image pull | ~30s | Cached after first pull |
| fastembed model load | ~15-30s | Downloads 2.5 GB ONNX on first ever start; cached in Docker layer |
| LangGraph compile | ~2s | Compiles supervisor + 3 specialist graphs |
| DB connection pool | ~3s | Opens connections to PG, CH, Neo4j |
| **Total cold start** | **~45-60s** | Subsequent starts: ~5-10s |

### Latency budget (per query)

| Step | Typical Time |
|------|-------------|
| Task classification (regex) | <1 ms |
| Model selection | <1 ms |
| Supervisor routing (Qwen 72B) | 2-5s |
| Specialist tool execution | 1-10s (depends on DB query) |
| Specialist LLM response | 3-8s |
| **Total (simple query)** | **6-15s** |
| **Total (pipeline query)** | **15-75s** (e.g., Graph RAG full synthesis) |

### Tips for better UX

1. **Show streaming events immediately** — the frontend gets `model_selection` and `routing` events within 3-5s, keeping users engaged.
2. **Pre-warm on deploy** — the Dockerfile pre-downloads the fastembed model into the Docker layer, so there's no download on first request.
3. **Keep-alive** — HF Spaces sleeps after 48h of inactivity (free tier). A simple cron pinging `/api/health` keeps it awake.
4. **Thread reuse** — reuse thread IDs for the same user/conversation to benefit from conversation memory.

---

## Quick Deployment Commands

```bash
# ── Local test ──
cd /Users/rahul/Desktop/Datathon
pip install -r server/requirements.txt
python server/app.py
# → http://localhost:7860/docs

# ── Docker local test ──
docker build -t eng-intel-api .
docker run -p 7860:7860 --env-file .env eng-intel-api
# → http://localhost:7860/docs

# ── HuggingFace Spaces ──
# 1. Create Space (Docker SDK) at huggingface.co/new-space
# 2. Add secrets in Space Settings
# 3. Push: agents/, server/, Dockerfile
# 4. Wait for build → https://<user>-<space>.hf.space/docs
```
