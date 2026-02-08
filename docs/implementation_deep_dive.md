# Engineering Intelligence Platform — Implementation Deep Dive

> **Complete technical documentation of every AI-native feature, its internal mechanics, and how a frontend should consume it.**
>
> Total codebase: **~7,500 lines** across 27 Python files, 21 tool functions, 5 LangGraph sub-graph pipelines, 3 specialist agents, 1 supervisor orchestrator.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Phase 0 — Foundation Layer](#2-phase-0--foundation-layer)
3. [Feature 4.3 — Multi-Model Routing](#3-feature-43--multi-model-routing)
4. [Feature 1.1 — Agentic RAG Pipeline](#4-feature-11--agentic-rag-pipeline)
5. [Feature 4.1 — Conversation Memory](#5-feature-41--conversation-memory)
6. [Feature 2.1 — Anomaly Detection](#6-feature-21--anomaly-detection-pipeline)
7. [Feature 2.3 — 1:1 Meeting Prep Agent](#7-feature-23--11-meeting-prep-agent)
8. [Feature 1.3 — Natural Language → SQL/Cypher](#8-feature-13--natural-language--sqlcypher)
9. [Feature 3.3 — Graph RAG Expert Discovery](#9-feature-33--graph-rag-expert-discovery)
10. [Feature 4.2 — Streaming Responses](#10-feature-42--streaming-responses--tool-call-visualization)
11. [Frontend Integration Guide](#11-frontend-integration-guide)
12. [API Endpoint Design (for FastAPI)](#12-api-endpoint-design-for-fastapi)
13. [Test Coverage Summary](#13-test-coverage-summary)

---

## 1. System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                        │
│  Chat UI  ·  Dashboard  ·  1:1 Prep  ·  Anomaly Alerts         │
└─────────────────────────┬────────────────────────────────────────┘
                          │ SSE / REST
┌─────────────────────────▼────────────────────────────────────────┐
│                    FastAPI Backend (to be built)                  │
│  /chat  ·  /stream  ·  /threads  ·  /health                     │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│                   Supervisor (LangGraph StateGraph)               │
│  • Classifies query → TaskType (regex + LLM)                    │
│  • Selects optimal model → ModelSelection                        │
│  • Routes to 1 of 3 specialists                                  │
│  • Manages conversation threads via MemorySaver                  │
└───┬──────────────┬─────────────────┬─────────────────────────────┘
    │              │                 │
    ▼              ▼                 ▼
┌────────┐  ┌────────────────┐  ┌──────────────────┐
│DORA_Pro│  │Resource_Planner│  │Insights_Specialist│
│ 5 tools│  │    6 tools     │  │     11 tools      │
└──┬─────┘  └──┬─────────────┘  └──┬───────────────┘
   │           │                   │
   ▼           ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Tool Layer (21 tools)                       │
│  postgres_tools · clickhouse_tools · neo4j_tools · vector_tools  │
│  rag_tools · anomaly_tools · prep_tools · nl_query_tools         │
│  graph_rag_tools · embedding_tools                               │
└──┬───────────┬───────────┬───────────┬───────────────────────────┘
   │           │           │           │
   ▼           ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Postgres│ │Clickhse│ │ Neo4j  │ │pgvector│
│ Aurora │ │ Cloud  │ │  Aura  │ │  1024d │
│18 empl │ │135 evts│ │ (graph)│ │32 embed│
└────────┘ └────────┘ └────────┘ └────────┘
```

### How the Supervisor Works

Every user message follows this flow:

1. **classify_task(query)** — regex-based task classification → `TaskType` enum
2. **select_model(task_type)** — lookup table → `ModelSelection` (model name, temperature, emoji)
3. **Supervisor LLM** (Qwen 72B) — reads the conversation, picks which specialist to route to (structured JSON output `{"next": "AGENT_NAME"}`)
4. **Specialist Agent** — `create_react_agent()` with the selected model and its tool list. The agent autonomously decides which tools to call, processes results, and generates a response.
5. **Back to Supervisor** — decides if the answer is complete (→ FINISH) or needs another specialist

The specialist agent's response is prepended with a model attribution header: `⚡ *[Hermes 3 8B]*\n\n...`

### Database Layer

| Database | Purpose | Data |
|----------|---------|------|
| **PostgreSQL Aurora** | Relational employee/team/project data | 18 employees, 4 teams, 14 projects, 22 assignments |
| **ClickHouse Cloud** | Time-series events & DORA metrics | 135 events, 65 daily DORA metric rows |
| **Neo4j Aura** | Knowledge graph (Developer → EXPERT_IN → Topic) | Connected, structure defined, falls back to synthetic data |
| **pgvector** | 1024-dim HNSW semantic embeddings | 32 embeddings (developer profiles, project descriptions, team overviews) |

All database clients are **singletons** with lazy connection, auto-reconnect, and health check methods. See `agents/utils/db_clients.py`.

---

## 2. Phase 0 — Foundation Layer

### 0.1 Schema Alignment
**What it does:** Fixed every SQL query across all tools to reference the actual database schema. All tools now use `employees` (not `users`), `allocated_percent` (not `allocation_percentage`), and correctly handle the fact that `projects` has no `team_id` column.

**Frontend relevance:** Without this, every database query would return errors. This is invisible to the frontend but critical — it means every tool call returns real data.

### 0.2 Real Embedding Pipeline
**What it does:** Replaced the fake `ILIKE` text search with real cosine similarity search over 1024-dimensional embeddings. Uses `BAAI/bge-large-en-v1.5` via the `fastembed` library (runs locally, no API call needed).

**File:** `agents/tools/embedding_tools.py`

**Key functions:**
- `generate_embedding(text) → list[float]` — single text → 1024-dim vector
- `generate_embeddings(texts) → list[list[float]]` — batch
- `cosine_similarity(a, b) → float` — numpy dot product
- `format_embedding(vec) → str` — pgvector SQL literal

**Frontend relevance:** Powers every "find similar" or "who has skills in X" query. The frontend doesn't interact with this directly — it's consumed internally by `semantic_search` and `find_developer_by_skills` tools.

### 0.3 Seed Embeddings
**What it does:** Generated and stored 32 real embeddings in the pgvector `embeddings` table:
- **Developer profiles** — concatenation of name, title, team, skills, bio
- **Project descriptions** — project name, description, tech stack
- **Team overviews** — team name, focus area, member list

**Frontend relevance:** These embeddings make semantic search work. When a user asks "who knows about Kubernetes?", the system embeds that query and finds the closest developer profiles by cosine similarity.

### 0.4 ClickHouse Real Queries
**What it does:** Replaced all hardcoded/synthetic ClickHouse tool responses with real SQL queries against the `events` and `dora_daily_metrics` tables. The three ClickHouse tools now execute:

| Tool | Query Summary |
|------|---------------|
| `get_deployment_metrics` | `SELECT ... FROM events` for deployment events in date range |
| `get_dora_metrics` | `SELECT avg(deployment_frequency), avg(lead_time_hours), avg(change_failure_rate), avg(mttr_hours) FROM dora_daily_metrics` with optional project/date filters + per-project breakdown |
| `get_developer_activity` | Per-developer event counts grouped by event_type over a date range |

**Frontend relevance:** DORA dashboards and developer activity charts now show real data, not placeholders.

---

## 3. Feature 4.3 — Multi-Model Routing

**File:** `agents/utils/model_router.py` (211 lines)

### What It Does
Every query is classified into one of 5 task types, and the optimal LLM is selected for that task:

| TaskType | Regex Keywords (examples) | Model Selected | Temperature |
|----------|--------------------------|----------------|-------------|
| `CODE_ANALYSIS` | sql, cypher, code, debug, refactor, lint, PR review | DeepSeek Coder V2 | 0.0 |
| `ANALYTICS` | dora, metric, deploy, failure rate, mttr, anomaly, trend | Llama 3.1 70B | 0.1 |
| `PLANNING` | plan, workload, capacity, risk, deadline, 1:1, meeting prep | Qwen 72B | 0.1 |
| `QUICK_LOOKUP` | who is, find developer, skill, expertise, list developers | Hermes 3 8B | 0.1 |
| `GENERAL` | (fallback — nothing matched) | Qwen 72B | 0.1 |

### How It Works
```
User query → classify_task(query) → (TaskType, reason)
                                          ↓
                                   select_model(task_type) → ModelSelection
                                          ↓
                                   { model_name, display_name, emoji, temperature }
```

The `ModelSelection` is packed into `AgentState.model_selection` and passed down to the specialist node, which creates (or retrieves from cache) an agent compiled with that specific model.

### Frontend Application
The frontend receives a `model_selection` event in the streaming response:
```json
{
  "event": "model_selection",
  "data": {
    "model": "Hermes 3 8B",
    "emoji": "⚡",
    "task_type": "quick_lookup",
    "reason": "Lightweight model for fast profile lookups"
  }
}
```

**UI rendering:** Display a chip/badge like `⚡ Hermes 3 8B` next to the response, or in a status bar: "Using Hermes 3 8B for quick lookup". This makes the multi-model capability visible to judges.

---

## 4. Feature 1.1 — Agentic RAG Pipeline

**File:** `agents/pipelines/rag_pipeline.py` (433 lines)

### What It Does
A self-correcting Retrieval-Augmented Generation pipeline that:
1. Embeds the query and searches pgvector
2. Grades each retrieved document for relevance
3. Rewrites the query if results are poor (up to 2 retries)
4. Generates a grounded answer citing sources
5. Checks for hallucinations and retries if detected

### Pipeline Graph (5 nodes)

```
START → retrieve → grade_documents → generate_answer → check_hallucination → END
              ↑                              │                     │
              └──────── rewrite_query ◄──────┘                     │
                   (if no relevant docs)     (if hallucination)    │
                                                                   ↓
                                                                  END
```

| Node | Model | What It Does |
|------|-------|-------------|
| `retrieve` | — (embedding only) | pgvector `<=>` search, top-8 results |
| `grade_documents` | Hermes 3 8B | JSON grading: `{"relevant": "yes"/"no"}` per doc, filters sim < 0.25 |
| `rewrite_query` | Hermes 3 8B | Rewrites query for better retrieval (max 2 rewrites) |
| `generate_answer` | Qwen 72B | Synthesizes grounded answer from relevant docs |
| `check_hallucination` | Hermes 3 8B | Boolean check: is the answer supported by the sources? |

### Frontend Application
Consumed via the `rag_search` tool on the Insights Specialist. The frontend doesn't call this directly — a user asks a complex question like "What are the main areas of expertise across the Platform Engineering team?" and the agent autonomously invokes `rag_search`.

**What the frontend sees:** A rich answer with a metadata footer:
```
[answer text]

---
📚 RAG Search | Sources: 4 documents | Retries: 0 | Hallucination check: passed
```

**UI rendering:** Parse the footer to show a "Sources" badge. Could expand into a collapsible "Sources" section showing the retrieved documents.

---

## 5. Feature 4.1 — Conversation Memory

**File:** `agents/utils/memory.py` (174 lines)

### What It Does
Thread-based conversation persistence using LangGraph's `MemorySaver` checkpointer. Each conversation thread maintains its own message history, so the agent remembers previous messages within a thread.

### API

| Method | Description |
|--------|-------------|
| `new_thread(title)` | Creates a thread with a 12-char hex ID, auto-evicts oldest if over limit |
| `list_threads()` | Returns all threads sorted by last_active descending |
| `delete_thread(id)` | Removes a thread |
| `get_config(thread_id)` | Returns `{"configurable": {"thread_id": id}}` for LangGraph |
| `touch_thread(id, count)` | Updates last_active timestamp and message count |
| `get_trimmed_messages(thread_id, max_messages)` | Trims old messages while preserving system messages |

### How Memory Works with the Supervisor
```
SupervisorAgent.query(message, thread_id="abc123")
    → graph.invoke(state, config={"configurable": {"thread_id": "abc123"}})
    → LangGraph MemorySaver stores/restores the full message list per thread
```

### Frontend Application
**This is one of the most important features for the frontend.** It enables:

1. **Multi-turn chat** — "Who is Alex Kumar?" → "What projects is he working on?" → "Is he overallocated?"
2. **Thread management UI** — list threads, switch between them, create new ones
3. **Session persistence** — conversations survive page refreshes (within the server session)

**API endpoints the frontend needs:**
```
POST   /threads              → { thread_id, title }
GET    /threads              → [{ thread_id, title, message_count, last_active }]
DELETE /threads/{id}         → 204
POST   /chat                 → { message, thread_id? } → streaming response
```

**UI rendering:** Standard chat interface with a thread sidebar. Each thread shows its title, message count, and last activity time.

---

## 6. Feature 2.1 — Anomaly Detection Pipeline

**File:** `agents/pipelines/anomaly_pipeline.py` (712 lines)

### What It Does
A 7-node pipeline that detects anomalies in DORA metrics and engineering activity, cross-references them with organizational context, generates actionable alerts, and self-evaluates their quality.

### Pipeline Graph (7 nodes)

```
START → fetch_metrics → compute_baselines → detect_anomalies
    → enrich_context → format_alert → evaluate_alert
    → [if score < 0.7] → refine_alert → END
    → [if score ≥ 0.7] → END
```

| Node | Model | What It Does |
|------|-------|-------------|
| `fetch_metrics` | — | ClickHouse: DORA aggregates, event counts, developer activity (configurable lookback days) |
| `compute_baselines` | — | ClickHouse: weekly averages + per-developer baselines (2× lookback period for historical comparison) |
| `detect_anomalies` | Llama 3.1 70B | Compares current vs baseline, outputs JSON array of anomalies with severity (critical/warning/info), metric, deviation %, affected entities |
| `enrich_context` | Qwen 72B | Cross-references anomalies with PostgreSQL employee/project data (names, roles, assignments) |
| `format_alert` | Qwen 72B | Generates formatted alert: severity emoji, title, metrics table, root cause analysis, recommendations |
| `evaluate_alert` | Hermes 3 8B | Self-evaluates alert quality on 5 criteria (score 0.0–1.0) |
| `refine_alert` | Qwen 72B | If score < 0.7, refines based on evaluation feedback |

### Frontend Application
Consumed via the `detect_anomalies` tool on the DORA_Pro specialist. A user asks "Are there any anomalies in our deployment metrics?" or "Check for problems in the last 14 days".

**What the frontend receives:**
```markdown
## 🚨 Anomaly Detection Report

### Critical Alerts
🔴 **Deployment Frequency Drop — API Gateway**
- Current: 0.5 deploys/day vs baseline 2.3 deploys/day (78% decrease)
- Affected: Alex Kumar, Priya Sharma
- Recommendation: Check CI/CD pipeline health...

### Metrics Summary
| Metric | Current | Baseline | Deviation |
|--------|---------|----------|-----------|
| ...    | ...     | ...      | ...       |

---
🚨 Anomaly Detection | Quality: 0.85/1.0 | Anomalies found: 3 | Lookback: 14 days
```

**UI rendering:**
- **Dashboard widget:** Severity-colored cards (🔴 critical, 🟡 warning, 🔵 info)
- **Alert detail panel:** Expandable sections for each anomaly
- **Metrics table:** Render as a comparison chart (current vs baseline)
- **Quality score:** Show as a confidence indicator

---

## 7. Feature 2.3 — 1:1 Meeting Prep Agent

**File:** `agents/pipelines/prep_pipeline.py` (528 lines)

### What It Does
Generates comprehensive 1:1 meeting preparation briefings by gathering data from all four databases, computing workload analytics, and using LLM to synthesize talking points.

### Pipeline Graph (5 nodes, linear)

```
START → resolve_developer → fetch_activity → compute_analytics
    → gather_peer_context → generate_briefing → END
```

| Node | Data Source | What It Gathers |
|------|-----------|-----------------|
| `resolve_developer` | PostgreSQL | Employee profile, team info, all project assignments with allocation % |
| `fetch_activity` | ClickHouse | 14-day summary, 7-day daily breakdown, last 10 events |
| `compute_analytics` | (computation) | Total allocation %, overallocated flag, per-project DORA metrics |
| `gather_peer_context` | ClickHouse + pgvector | Top co-contributors (30-day event co-occurrence), skill embedding similarity |
| `generate_briefing` | Qwen 72B | Structured briefing with 6 sections |

### Briefing Structure
The LLM generates a briefing with these sections:
1. **Quick Profile** — Name, title, team, allocation status
2. **Recent Accomplishments** — Based on commit/deploy/review activity
3. **Potential Concerns** — Overallocation, declining activity, failed deployments
4. **Suggested Talking Points** — Specific, actionable conversation starters
5. **Growth Opportunities** — Based on skills, collaboration patterns, expertise gaps
6. **Key Metrics** — Deployment frequency, lead time, failure rate, activity trend

### Frontend Application
Two tools are exposed:
- `prepare_one_on_one(developer_name)` → Full briefing document
- `get_talking_points(developer_name)` → Condensed numbered list

**Example interaction:** "Prepare for my 1:1 with Priya Sharma"

**UI rendering:**
- **Dedicated 1:1 prep page:** Select a developer from a dropdown → generates briefing
- **Tabbed layout:** Quick Profile | Accomplishments | Concerns | Talking Points | Growth | Metrics
- **Print/export:** The briefing is markdown-formatted, easy to render or export as PDF
- **Schedule integration:** Could link to calendar for upcoming 1:1s

---

## 8. Feature 1.3 — Natural Language → SQL/Cypher

**File:** `agents/pipelines/nl_query_pipeline.py` (687 lines)

### What It Does
Translates natural language questions into SQL (PostgreSQL or ClickHouse) or Cypher (Neo4j) queries, executes them, auto-corrects on errors, and summarizes results in plain English.

### Pipeline Graph (7 nodes with self-correction loop)

```
START → classify_database → generate_query → validate_query
    → [valid] → execute_query → summarize_results → END
    → [invalid] → fix_query → validate_query (retry, max 3)
    → [exhausted] → give_up → END
    
execute_query:
    → [error] → fix_query → validate_query
    → [success] → summarize_results → END
```

| Node | Model | What It Does |
|------|-------|-------------|
| `classify_database` | Hermes 3 8B | Routes to postgres/clickhouse/neo4j; keyword fallback |
| `generate_query` | Qwen 72B | Generates SQL/Cypher from NL + full schema context |
| `validate_query` | Hermes 3 8B + rules | Structural validation (no destructive ops, valid tables, schema-aware checks like "projects has NO team_id") + LLM semantic validation |
| `execute_query` | — | Runs on appropriate DB client |
| `fix_query` | Qwen 72B | Fixes query using error message (max 3 retries) |
| `summarize_results` | Qwen 72B | Executive-level NL summary from raw results |
| `give_up` | — | Error summary when retries exhausted |

### Embedded Schema Knowledge
The pipeline has **full schema definitions hardcoded** so the LLM always knows the exact table structure:

```python
_PG_SCHEMA = """
employees: id (UUID PK), full_name, email, title, role, hourly_rate, level, team_id (FK→teams.id)
teams: id (UUID PK), name, description
projects: id (UUID PK), name, description, status, priority, start_date, end_date
    ⚠️ projects has NO team_id column
project_assignments: id (UUID PK), employee_id (FK), project_id (FK), role, allocated_percent, start_date
    ⚠️ Column is allocated_percent NOT allocation_percentage
embeddings: id, content_type, content_id, content, embedding (vector(1024))
"""
```

### Frontend Application
Consumed via the `natural_language_query` tool. Any specialist can use it, but it's primarily on DORA_Pro.

**Example interactions:**
- "How many employees are there?" → `SELECT COUNT(*) FROM employees` → "There are 18 employees"
- "How many events happened last week?" → `SELECT count(*) FROM events WHERE ...` → "135 events"
- "List all team names" → `SELECT name FROM teams` → "Platform Engineering, Frontend Team, Data Engineering, DevOps"

**What the frontend receives:**
```
There are 18 employees in the organization.

---
💬 NL Query | DB: postgres | Query: SELECT COUNT(*) FROM employees | Rows: 1 | Retries: 0
```

**UI rendering:**
- **Query explorer widget:** Show the generated SQL/Cypher in a collapsible code block
- **Results table:** Render raw results as a sortable table
- **Natural language summary:** Display above the table
- **Database badge:** Show which database was queried (PostgreSQL / ClickHouse / Neo4j)

---

## 9. Feature 3.3 — Graph RAG Expert Discovery

**File:** `agents/pipelines/graph_rag_pipeline.py` (614 lines)

### What It Does
Combines pgvector semantic search with Neo4j knowledge graph traversal to find the best expert for a given topic. Uses weighted score fusion and LLM-generated explanations.

### Pipeline Graph (5 nodes, linear)

```
START → vector_search → graph_search → fuse_and_rank
    → explain_recommendations → synthesize → END
```

| Node | Data Source | What It Does |
|------|-----------|-------------|
| `vector_search` | pgvector | Embeds topic query, cosine similarity search on `developer_profile` embeddings, joins with employees/teams |
| `graph_search` | Neo4j | 3 Cypher queries (EXPERT_IN, CONTRIBUTED_TO, COLLABORATES_WITH); falls back to synthetic data if Neo4j is empty |
| `fuse_and_rank` | (computation) | Weighted fusion: `0.6 × vector_score + 0.4 × graph_score`, union of candidates, sorted descending |
| `explain_recommendations` | Qwen 72B | Generates 2-3 sentence explanation per candidate in a single batch prompt |
| `synthesize` | Qwen 72B | Composes an "Expert Discovery Report" with executive summary, ranked recommendations, methodology note |

### Fusion Logic
```python
combined_score = VECTOR_WEIGHT * vector_score + GRAPH_WEIGHT * graph_score
# VECTOR_WEIGHT = 0.6, GRAPH_WEIGHT = 0.4
```

Candidates appearing in only one source get the single source score × its weight. The final ranking considers both semantic similarity (from embeddings) and structural authority (from graph relationships).

### Two Tools, Two Speeds

| Tool | Pipeline | Speed | Use Case |
|------|----------|-------|----------|
| `find_expert_for_topic(topic, limit)` | Full Graph RAG (5 nodes, 2 LLM calls) | ~40-75s | "Who can help with database optimization?" — deep, explained recommendations |
| `quick_expert_search(topic, limit)` | Vector-only (`find_developer_by_skills`) | ~1-2s | "Who knows Python?" — fast skill matching, no LLM |

### Frontend Application
**Example interaction:** "Find me an expert in React TypeScript"

**What the frontend receives:**
```markdown
### Expert Discovery Report

#### Executive Summary
Top experts for React TypeScript include Sneha Patel and Vikram Rao...

#### Recommended Experts

1. **Sneha Patel** (Combined Score: 0.68)
   Frontend Team · Senior Engineer
   Sneha has extensive experience with React and TypeScript frameworks,
   having contributed to multiple frontend projects...

2. **Vikram Rao** (Combined Score: 0.55)
   ...

#### Methodology
Results combine semantic similarity (60%) from developer profile embeddings
with knowledge graph analysis (40%) of expertise relationships...

---
🧠 Graph RAG | Candidates: 3 | Vector matches: 6 | Graph matches: 5 | Time: 42.3s
```

**UI rendering:**
- **Expert cards:** Card per developer with photo placeholder, name, team, score bar
- **Score breakdown:** Split bar showing vector vs graph contribution
- **Explanation text:** Expandable per-card explanation
- **Quick vs Deep toggle:** Button to switch between `quick_expert_search` (instant) and `find_expert_for_topic` (thorough)

---

## 10. Feature 4.2 — Streaming Responses & Tool Call Visualization

**File:** `agents/utils/streaming.py` (472 lines)

### What It Does
A complete streaming event protocol that gives the frontend real-time visibility into what the agent system is doing — which model was selected, which agent is working, which tools are being called, and the response as it's generated.

### Event Types (12)

| Event | When Emitted | Data Shape |
|-------|-------------|------------|
| `stream_start` | Stream begins | `{ query, thread_id }` |
| `stream_end` | Stream complete | `{ total_tokens, elapsed_s }` |
| `model_selection` | Supervisor selects model | `{ model, emoji, task_type, reason }` |
| `routing` | Supervisor routes to specialist | `{ agent }` |
| `agent_start` | Specialist begins work | `{ agent, model }` |
| `agent_end` | Specialist finishes | `{ agent, elapsed_s }` |
| `tool_start` | Tool invocation begins | `{ tool, args }` |
| `tool_end` | Tool returns result | `{ tool, result_preview, elapsed_s }` |
| `token` | LLM generates a token | `{ text }` |
| `response` | Complete response chunk | `{ content }` |
| `status` | Informational status | `{ message }` |
| `error` | Error occurred | `{ message }` |

### Two Streaming Modes

| Method | LangGraph Mode | Granularity | Best For |
|--------|---------------|-------------|----------|
| `stream_query()` | default (per-node updates) | Response-level: emits complete messages | Simpler frontends, reliable |
| `stream_query_tokens()` | `stream_mode="messages"` | Token-level: emits individual tokens | ChatGPT-like typing effect |

### SSE Format
Every event serializes to Server-Sent Events:
```
event: tool_start
data: {"event":"tool_start","data":{"tool":"semantic_search","args":{"query":"Python"}},"timestamp":1707400000.0,"metadata":{}}

event: token
data: {"event":"token","data":{"text":"Here"},"timestamp":1707400001.0,"metadata":{"agent":"Insights_Specialist"}}
```

### Frontend Application
**This is the most important feature for frontend UX.** It transforms the experience from "loading spinner → final answer" to a live, interactive visualization of the AI thinking process.

**UI rendering (recommended):**

1. **Status bar:** Shows current state: `⚡ Using Hermes 3 8B for quick lookup`
2. **Routing indicator:** `↪ Routing to Insights_Specialist`
3. **Tool call timeline:**
   ```
   🔍 semantic_search (query="Python")
     ✓ 0.8s → 5 matches
   👤 get_developer (name="Alex Kumar")
     ✓ 0.3s → Senior Engineer
   ```
4. **Streaming response:** Characters appear as tokens arrive (typewriter effect)
5. **Completion stats:** `42 tokens · 3.1s`

**The `StreamBuffer` class** enables thread-safe producer/consumer patterns for WebSocket implementations.

**The `format_events_as_sse()` function** is ready to plug directly into FastAPI's `StreamingResponse`.

---

## 11. Frontend Integration Guide

### What Each Feature Looks Like to the Frontend

| Feature | User Trigger | Response Type | Latency | UI Component |
|---------|-------------|---------------|---------|-------------|
| **Multi-Model Routing** | (automatic) | `model_selection` event | 0ms | Status badge |
| **Agentic RAG** | Complex knowledge question | Markdown + sources footer | 5-15s | Chat bubble + sources panel |
| **Conversation Memory** | Thread management | Thread list / chat history | 0ms | Thread sidebar |
| **Anomaly Detection** | "Check for anomalies" | Markdown report with severity | 15-30s | Alert dashboard cards |
| **1:1 Prep** | "Prepare for 1:1 with [name]" | Structured briefing | 20-40s | Tabbed briefing view |
| **NL→SQL/Cypher** | Data questions | Answer + generated query | 10-20s | Results table + SQL viewer |
| **Graph RAG Expert** | "Find expert in [topic]" | Ranked expert cards | 40-75s (full) / 1-2s (quick) | Expert cards with scores |
| **Streaming** | (automatic) | SSE event stream | Real-time | Tool timeline + typewriter text |

### Response Format Convention
All pipeline tools append a metadata footer after `---`:
```
[main response content]

---
📊 [Pipeline Name] | key1: val1 | key2: val2 | Time: Xs
```

The frontend should:
1. Split on `\n---\n`
2. Render the main content as Markdown
3. Parse the footer into a metadata badge/chip

### Error Handling
If the agent encounters an error, the streaming response includes:
```json
{ "event": "error", "data": { "message": "Connection timeout to ClickHouse" } }
```

The frontend should display errors gracefully and allow retry.

---

## 12. API Endpoint Design (for FastAPI)

Here's the recommended FastAPI endpoint structure to expose all features:

### Core Endpoints

```
POST   /api/chat              — Main chat endpoint (streaming SSE)
POST   /api/chat/sync         — Synchronous chat (for simple integrations)
POST   /api/threads           — Create a new conversation thread
GET    /api/threads           — List all threads
DELETE /api/threads/{id}      — Delete a thread
GET    /api/health            — System health check (all DB connections)
```

### Chat Request/Response

**Request:**
```json
{
  "message": "Find developers with Python expertise",
  "thread_id": "abc123def456",    // optional — omit for ephemeral
  "stream": true                   // optional — default true
}
```

**Response (streaming — SSE):**
```
event: stream_start
data: {"event":"stream_start","data":{"query":"Find developers with Python expertise","thread_id":"abc123def456"},"timestamp":1707400000.0}

event: model_selection
data: {"event":"model_selection","data":{"model":"Hermes 3 8B","emoji":"⚡","task_type":"quick_lookup","reason":"..."},"timestamp":1707400001.0}

event: routing
data: {"event":"routing","data":{"agent":"Insights_Specialist"},"timestamp":1707400002.0}

event: tool_start
data: {"event":"tool_start","data":{"tool":"find_developer_by_skills","args":{"skills":"Python"}},"timestamp":1707400003.0}

event: tool_end
data: {"event":"tool_end","data":{"tool":"find_developer_by_skills","result_preview":"5 matches","elapsed_s":0.8},"timestamp":1707400004.0}

event: response
data: {"event":"response","data":{"content":"Here are developers with Python expertise:\n\n1. **Alex Kumar**..."},"timestamp":1707400010.0}

event: stream_end
data: {"event":"stream_end","data":{"total_tokens":42,"elapsed_s":10.5},"timestamp":1707400010.5}
```

**Response (sync — JSON):**
```json
{
  "response": "Here are developers with Python expertise:\n\n1. **Alex Kumar**...",
  "thread_id": "abc123def456",
  "model_used": "Hermes 3 8B",
  "task_type": "quick_lookup",
  "elapsed_s": 10.5
}
```

### Frontend SSE Consumption (JavaScript)
```javascript
const evtSource = new EventSource('/api/chat?message=...');
// or for POST requests, use fetch() with ReadableStream:

const response = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message, thread_id })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // Parse SSE events from text
  for (const event of parseSSE(text)) {
    switch (event.type) {
      case 'model_selection': updateStatusBar(event.data); break;
      case 'tool_start': addToolToTimeline(event.data); break;
      case 'tool_end': completeToolInTimeline(event.data); break;
      case 'response': appendToChat(event.data.content); break;
      case 'error': showError(event.data.message); break;
    }
  }
}
```

---

## 13. Test Coverage Summary

| Feature | Test File | Tests | Status |
|---------|-----------|-------|--------|
| Multi-Model Routing (4.3) | `scripts/test_model_router.py` | 40/40 | ✅ |
| Agentic RAG (1.1) | `scripts/test_rag_pipeline.py` | 13/13 | ✅ |
| Conversation Memory (4.1) | `scripts/test_memory.py` | 20/20 | ✅ |
| Anomaly Detection (2.1) | `scripts/test_anomaly_pipeline.py` | 10/10 | ✅ |
| 1:1 Prep Agent (2.3) | `scripts/test_prep_pipeline.py` | 12/12 | ✅ |
| NL→SQL/Cypher (1.3) | `scripts/test_nl_query_pipeline.py` | 12/12 | ✅ |
| Graph RAG Expert (3.3) | `scripts/test_graph_rag_pipeline.py` | 31/31 | ✅ |
| Streaming (4.2) | `scripts/test_streaming.py` | 45/45 | ✅ |
| **Total** | **8 test files** | **183/183** | **✅** |

Each test suite has three tiers:
- **Unit tests** — pure logic, no DB or LLM calls
- **Integration tests** — component wiring, imports, graph compilation
- **Live LLM tests** — end-to-end with real Featherless.ai API calls and real database queries
