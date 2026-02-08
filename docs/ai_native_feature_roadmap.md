# AI-Native Feature Roadmap & Plan of Action

> **Engineering Intelligence Platform — GenAI Feature Strategy**
>
> This document replaces the previous CRUD-focused roadmap with a **genuine AI-native** implementation plan.
> Every feature leverages multi-agent orchestration, tool calling, RAG, or agentic workflows — not simple database queries.

---

## Executive Summary

**The Problem:** Our current roadmap features are thinly-veiled SQL queries wrapped in agent tools. A frontend calling `get_developer_workload()` is not AI — it's a REST API with extra steps.

**The Pivot:** Every feature below requires the LLM to **reason**, **plan**, **retrieve-and-synthesize**, or **self-correct**. These are capabilities a database query cannot replicate.

**What We Have Working:**
- ✅ LangGraph supervisor routing to 3 specialist agents
- ✅ Featherless.ai multi-model inference (Qwen 72B, Llama 3.1 70B, Hermes 3 8B, DeepSeek Coder V2)
- ✅ PostgreSQL with real data (users, teams, projects, assignments)
- ✅ pgvector with 1024-dim HNSW index (ready for embeddings)
- ✅ Neo4j Aura connected (graph structure defined)
- ✅ ClickHouse Cloud connected (time-series ready)

**What's Broken / Placeholder:**
- ❌ `semantic_search` uses ILIKE text match, NOT vector cosine similarity
- ❌ No embedding generation pipeline (pgvector table exists but can't create embeddings)
- ❌ ClickHouse `get_deployment_metrics` and `get_developer_activity` are 100% hardcoded
- ❌ All Neo4j tools fall back to synthetic data
- ❌ `users` table referenced in code but expanded schema defines `employees`
- ❌ DeepSeek Coder V2 model is configured but completely unused
- ❌ Zero write/action tools — agents can only read, never act
- ❌ No conversation memory or persistence
- ❌ No human-in-the-loop workflows

---

## 🔴 Phase 0: Foundation Fixes (BLOCKER — Do First)

*These are not features. These are prerequisites that unblock everything else.*

| # | Fix | What's Wrong | Action | Effort |
|---|-----|-------------|--------|--------|
| 0.1 | **Schema Alignment** | `postgres_tools.py` queries `users` but DB has `employees` | Update all SQL in postgres_tools.py to reference correct table names | 1 hour |
| 0.2 | **Real Embedding Pipeline** | `semantic_search` does ILIKE, not cosine similarity | Integrate llama-text-embed-v2 (1024-dim) via Featherless or a local embedding endpoint. Add `generate_embedding()` utility. Update `semantic_search` to use `1 - (embedding <=> query_vec)` | 3-4 hours |
| 0.3 | **Seed Embeddings** | pgvector table has no real embeddings | Write a script that reads `employees`, `projects`, `teams` and generates profile embeddings. Store in `embeddings` table. | 2 hours |
| 0.4 | **ClickHouse Real Data** | `get_deployment_metrics` and `get_developer_activity` are hardcoded dicts | Either: (a) Create ClickHouse tables and seed with synthetic-but-queryable data via INSERT, or (b) rewrite tools to query real tables. Remove hardcoded fallbacks. | 2-3 hours |
| 0.5 | **Neo4j Graph Seeding** | All Cypher queries fail, tools return hardcoded synthetic data | Seed Neo4j with nodes/edges derived from PostgreSQL data (employees → Developer nodes, project_assignments → WORKS_ON edges, etc.) | 2-3 hours |

**Total Phase 0: ~12 hours. This unblocks ALL features below.**

---

## 🟢 Phase 1: Agentic RAG & Intelligent Retrieval

*Goal: Make the agents actually use AI to find, reason over, and synthesize information — not just run SQL.*

### Feature 1.1: Agentic RAG with Self-Correction
**Pattern:** Self-Reflective RAG (inspired by CRAG + Self-RAG papers)

**What it does:**
When a user asks "Who can help me with the payment service?", the agent:
1. Generates an embedding of the query
2. Retrieves top-k candidates from pgvector (cosine similarity)
3. **Grades** each retrieved document for relevance (LLM call)
4. If results are poor, **rewrites the query** and re-retrieves
5. Generates a final answer grounded in verified context
6. **Self-checks** the answer for hallucination against source documents

**Why this is AI, not CRUD:** The retrieval loop with grading, query rewriting, and hallucination checking is a multi-step agentic workflow that cannot be replicated by a SQL query.

**LangGraph Implementation:**
```
START → generate_embedding → retrieve_from_pgvector → grade_documents
    ├── all_relevant → generate_answer → check_hallucination
    │       ├── passes → END
    │       └── fails → rewrite_query → retrieve_from_pgvector (loop)
    └── irrelevant → rewrite_query → retrieve_from_pgvector (loop)
```

**Tools Required:**
- `generate_embedding(text) → vector[1024]` — New tool, calls embedding model
- `vector_similarity_search(embedding, top_k) → docs` — Rewrite of current `semantic_search`
- `grade_document_relevance(query, document) → relevant|irrelevant` — LLM grader
- `check_hallucination(answer, source_docs) → supported|not_supported` — LLM checker

**Models:**
- Embedding: llama-text-embed-v2 (1024-dim) or any Featherless-hosted embedding model
- Grading: Hermes 3 8B (fast, good at binary classification)
- Generation: Qwen 72B (strong reasoning)

**Effort:** 6-8 hours | **Impact:** ⭐⭐⭐⭐⭐ (Core differentiator)

---

### Feature 1.2: Multi-Database Fusion Retrieval
**Pattern:** Orchestrator-Worker with parallel tool execution

**What it does:**
For complex queries like "Which overloaded developers have expertise in the billing service and could be reassigned?", the system:
1. Supervisor identifies this needs **multiple data sources**
2. Spawns parallel worker agents:
   - Worker A: Query pgvector for "billing service expertise" (semantic)
   - Worker B: Query PostgreSQL for workload data (structured)
   - Worker C: Query Neo4j for collaboration graph around billing (graph)
3. **Fusion node** combines results: intersects skill matches with workload data and graph context
4. LLM synthesizes a **reasoned recommendation** with justification

**Why this is AI, not CRUD:** No single SQL query can simultaneously do semantic similarity search, relational joins, and graph traversal, then reason over the combined results.

**LangGraph Implementation:**
```
START → plan_retrieval_strategy (LLM decides which DBs to query)
    → [parallel] pgvector_worker | postgres_worker | neo4j_worker
    → fusion_node (combine & deduplicate)
    → synthesize_recommendation (LLM reasoning over fused context)
    → END
```

**Tools Required:**
- `plan_retrieval_strategy(query) → List[DataSource]` — LLM decides which databases
- `pgvector_search(query)` — Semantic vector search
- `postgres_structured_query(query)` — Natural language to SQL
- `neo4j_graph_query(query)` — Natural language to Cypher
- `fuse_results(results_list) → unified_context` — Deduplication + ranking

**Effort:** 8-10 hours | **Impact:** ⭐⭐⭐⭐⭐ (Major wow factor for demos)

---

### Feature 1.3: Natural Language to Multi-DB Query (Text-to-SQL/Cypher)
**Pattern:** Prompt chaining with validation

**What it does:**
Leadership asks: "What's the average deployment frequency for teams with more than 5 members?"
1. LLM analyzes the question and identifies required data sources
2. Generates SQL (for PostgreSQL/ClickHouse) or Cypher (for Neo4j)
3. **Validates** the generated query against the schema (second LLM call)
4. Executes the query
5. If query fails, **self-corrects** using the error message
6. Translates raw results into a natural language executive summary

**Why this is AI, not CRUD:** The query generation, validation, self-correction loop, and natural language synthesis are all LLM-powered. The user never writes SQL.

**LangGraph Implementation:**
```
START → identify_data_sources → generate_query → validate_query
    ├── valid → execute_query → summarize_results → END
    └── invalid → fix_query → validate_query (loop, max 3 retries)
```

**Tools Required:**
- `get_schema_context(db_name) → schema_description` — Returns relevant table schemas
- `generate_sql(question, schema) → sql_string` — LLM generates query
- `validate_sql(sql, schema) → valid|error` — LLM checks for correctness
- `execute_sql(sql, db) → results` — Runs against Postgres or ClickHouse
- `generate_cypher(question, schema) → cypher_string` — For Neo4j queries
- `summarize_for_leadership(results, original_question) → text` — Executive summary

**Model:** DeepSeek Coder V2 for SQL/Cypher generation (finally using the unused model!)

**Effort:** 6-8 hours | **Impact:** ⭐⭐⭐⭐ (Leadership loves natural language queries)

---

## 🔵 Phase 2: Autonomous Agent Workflows

*Goal: Agents that don't just answer questions — they proactively detect, alert, and recommend.*

### Feature 2.1: Anomaly Detection & Alert Agent
**Pattern:** Evaluator-Optimizer loop with scheduled triggers

**What it does:**
A background agent runs on a schedule (or event trigger) and:
1. Queries the latest metrics from ClickHouse (commits, deploys, PR activity)
2. Compares against historical baselines using **LLM reasoning** (not just threshold rules)
3. For each anomaly detected, generates a **severity score** and **root cause hypothesis**
4. If severity is high, drafts an alert with recommended actions
5. **Self-evaluates** the alert quality before sending

**Example output:**
> 🔴 **Anomaly Detected — Team Backend**
> Deployment frequency dropped 70% this week (from 12 to 3 deploys).
> **Probable Cause:** 2 senior developers (Alex, Priya) have 0 commits since Tuesday. Cross-referencing with project assignments shows both are allocated to "Migration v3" which has no recent activity.
> **Recommendation:** Check if Migration v3 is blocked. Consider reassigning to unblock deployment pipeline.

**Why this is AI, not CRUD:** Rules-based alerting (threshold > X → alert) is not AI. Here the LLM reasons about *why* the anomaly occurred by cross-referencing multiple data sources, generates a hypothesis, and recommends actions.

**LangGraph Implementation:**
```
START → fetch_current_metrics → fetch_historical_baseline
    → detect_anomalies (LLM compares current vs baseline)
    → [for each anomaly] investigate_root_cause (multi-tool chain)
    → generate_alert_with_recommendation
    → evaluate_alert_quality (LLM self-check)
    ├── good → deliver_alert → END
    └── poor → refine_alert → evaluate_alert_quality (loop)
```

**Tools Required:**
- `fetch_metrics(period) → metrics_dict` — ClickHouse aggregation
- `fetch_baseline(metric, period) → baseline_dict` — Historical comparison
- `investigate_context(anomaly) → context` — Multi-DB cross-reference
- `generate_alert(anomaly, context, recommendation) → alert_text` — LLM drafting
- `evaluate_alert(alert_text) → quality_score` — LLM self-evaluation

**Effort:** 8-10 hours | **Impact:** ⭐⭐⭐⭐⭐ (Proactive AI — huge differentiator)

---

### Feature 2.2: Intelligent Sprint Report Generator
**Pattern:** Orchestrator-Worker with aggregation and synthesis

**What it does:**
Every Friday (or on-demand), generates a comprehensive engineering report by:
1. **Orchestrator** plans which metrics to gather
2. Spawns parallel workers:
   - DORA metrics worker (ClickHouse)
   - Developer productivity worker (PostgreSQL + ClickHouse)
   - Risk assessment worker (cross-DB analysis)
   - Collaboration health worker (Neo4j graph analysis)
3. Each worker retrieves data AND generates a **section narrative** (not raw numbers)
4. **Synthesizer** combines all sections into a coherent executive report
5. Adapts tone for the target audience (technical vs. leadership)

**Why this is AI, not CRUD:** Each section requires the LLM to interpret metrics, identify trends, compare against goals, and write narrative prose. The final synthesis requires understanding how different sections relate to each other.

**LangGraph Implementation (using Send API for dynamic workers):**
```
START → plan_report_sections (LLM decides sections based on available data)
    → [Send] worker_1 | worker_2 | worker_3 | worker_4
    → aggregate_sections
    → synthesize_executive_summary (LLM writes coherent narrative)
    → format_for_audience (technical / leadership / HR)
    → END
```

**Models:**
- Workers: Hermes 3 8B (fast, parallel execution)
- Synthesizer: Qwen 72B (strong reasoning + writing)

**Effort:** 6-8 hours | **Impact:** ⭐⭐⭐⭐ (Tangible output leadership can see)

---

### Feature 2.3: Developer 1:1 Prep Agent
**Pattern:** Multi-step prompt chain with RAG context injection

**What it does:**
Before a manager's 1:1 meeting with a developer, the agent:
1. Retrieves the developer's recent activity (commits, PRs, tickets completed)
2. Retrieves their project assignments and workload
3. Finds their collaboration patterns from Neo4j
4. Retrieves any previous 1:1 notes or check-in history (if available)
5. **Synthesizes** a personalized briefing with:
   - Talking points ("Alice shipped the auth refactor — acknowledge this")
   - Concerns ("Her commit frequency dropped 40% last week")
   - Growth suggestions ("She's been working solo — consider pairing her with the Platform team")
   - Questions to ask ("How's the migration going? No commits in 5 days.")

**Why this is AI, not CRUD:** The briefing requires interpretation of raw data, emotional intelligence in framing concerns, and creative suggestion generation. No SQL query produces "acknowledge this achievement."

**Tools Required:**
- All existing postgres/clickhouse/neo4j tools for data gathering
- `generate_briefing(developer_data, history) → briefing_doc` — LLM synthesis
- `suggest_talking_points(activity_data) → points[]` — LLM creative reasoning

**Effort:** 4-6 hours | **Impact:** ⭐⭐⭐⭐ (Managers love this — direct daily value)

---

## 🟡 Phase 3: Advanced Multi-Agent Patterns

*Goal: Showcase sophisticated AI architecture — hierarchical agents, human-in-the-loop, and reflection.*

### Feature 3.1: Resource Reallocation Advisor with Human-in-the-Loop
**Pattern:** Agent workflow with LangGraph `interrupt()` for human approval

**What it does:**
When the system detects a resource imbalance:
1. Resource agent identifies the problem ("Project Alpha has 3 idle devs, Project Beta is 2 sprints behind")
2. Insights agent finds best candidates using semantic skill matching (pgvector) + graph context (Neo4j)
3. Agent generates a **reallocation proposal** with reasoning
4. **PAUSES execution** and presents the proposal to the manager for approval
5. Manager approves/rejects/modifies
6. If approved, agent executes the change (writes to DB, optionally updates Jira)

**Why this is AI, not CRUD:** The combination of multi-agent collaboration (resource + insights agents working together), semantic skill matching, graph-aware recommendations, and human-in-the-loop approval is a genuinely sophisticated agentic workflow.

**LangGraph Implementation:**
```
START → detect_resource_imbalance (Resource Agent)
    → find_reallocation_candidates (Insights Agent — pgvector + Neo4j)
    → generate_proposal (LLM reasoning over combined data)
    → INTERRUPT (human-in-the-loop — manager reviews)
    ├── approved → execute_reallocation → notify_stakeholders → END
    ├── modified → adjust_proposal → INTERRUPT (loop)
    └── rejected → log_decision → END
```

**New Capabilities Required:**
- LangGraph `interrupt()` / checkpointing for human-in-the-loop
- Write tools: `update_assignment(dev_id, project_id)`, `create_notification()`
- State persistence (LangGraph checkpointer with PostgreSQL or SQLite)

**Effort:** 10-12 hours | **Impact:** ⭐⭐⭐⭐⭐ (The "autonomous agent that still asks humans" demo is extremely compelling)

---

### Feature 3.2: CI/CD Failure Diagnosis Agent
**Pattern:** Specialized code agent with DeepSeek Coder V2 + chain-of-thought

**What it does:**
When a CI/CD pipeline fails:
1. Agent retrieves the failure logs from ClickHouse
2. **DeepSeek Coder V2** analyzes the logs to identify the root cause
3. Agent retrieves relevant code context from the repository (via git tools or embeddings)
4. Generates a **diagnosis** with:
   - Root cause identification
   - Affected files/functions
   - Suggested fix (code snippet)
   - Similar past failures and their resolutions (RAG over historical failures)
5. Posts diagnosis to Slack or creates a Jira comment

**Why this is AI, not CRUD:** Using a specialized code LLM to analyze logs, cross-reference with code, and generate fix suggestions is peak GenAI.

**Model:** DeepSeek Coder V2 (finally using the 4th configured model!)

**Tools Required:**
- `get_failure_logs(pipeline_id) → logs` — ClickHouse
- `analyze_code_context(file_path) → code_snippet` — Retrieval
- `search_similar_failures(error_signature) → past_failures[]` — pgvector RAG
- `generate_diagnosis(logs, code, history) → diagnosis` — DeepSeek Coder V2
- `suggest_fix(diagnosis) → code_fix` — DeepSeek Coder V2

**Effort:** 8-10 hours | **Impact:** ⭐⭐⭐⭐⭐ (Tangible automation — "AI that fixes your build")

---

### Feature 3.3: Knowledge Graph-Powered Expert Discovery
**Pattern:** Graph RAG — combining Neo4j graph traversal with vector similarity

**What it does:**
"Who can help me debug the payment processing timeout?"
1. Agent generates embedding of the query → pgvector search for skill-matched developers
2. Agent queries Neo4j for:
   - Who has `CONTRIBUTED_TO` the payment service
   - Who `COLLABORATES_WITH` the payment team
   - Who is `EXPERT_IN` related topics (distributed systems, API design)
3. **Graph RAG fusion**: combines vector similarity scores with graph centrality/PageRank
4. Ranks candidates by combined score: `0.6 * semantic_similarity + 0.4 * graph_relevance`
5. Returns ranked list with **explanations** for each recommendation

**Why this is AI, not CRUD:** The fusion of vector similarity with graph traversal, combined with LLM-generated explanations for why each person is recommended, is a novel AI pattern.

**Tools Required:**
- `vector_skill_search(query) → [(dev_id, similarity_score)]`
- `graph_expertise_search(topic) → [(dev_id, graph_score, path)]`
- `fuse_and_rank(vector_results, graph_results, weights) → ranked_list`
- `explain_recommendation(dev, scores, context) → explanation` — LLM narration

**Effort:** 6-8 hours | **Impact:** ⭐⭐⭐⭐ (Novel Graph RAG — judges will notice)

---

## 🟣 Phase 4: Demo-Ready Polish & Integration

*Goal: Make everything presentable and interconnected.*

### Feature 4.1: Conversational Memory & Context Persistence
**Pattern:** LangGraph checkpointer with thread-based memory

**What it does:**
- Users can have multi-turn conversations: "Show me Team Alpha's velocity" → "Compare that with last quarter" → "Who was added to the team since then?"
- Agent remembers previous context within a thread
- Cross-references previous answers when synthesizing new ones

**Implementation:**
- Add `MemorySaver` or `SqliteSaver` checkpointer to the LangGraph compilation
- Thread ID management for conversation tracking
- System prompt update to reference conversation history

**Effort:** 3-4 hours | **Impact:** ⭐⭐⭐ (Expected by judges, table-stakes for agent demo)

---

### Feature 4.2: Streaming Responses with Tool Call Visualization
**Pattern:** LangGraph streaming with `stream_mode="messages"` + frontend SSE

**What it does:**
- Agent responses stream token-by-token to the frontend
- Tool calls are shown in real-time: "🔍 Searching pgvector for payment experts..." → "📊 Querying workload data..." → "🧠 Synthesizing recommendation..."
- Shows the reasoning chain visually (which tools were called, what was retrieved)

**Why this matters:** Makes the multi-agent system feel alive. Judges can see the AI thinking, not just a loading spinner → final answer.

**Effort:** 4-6 hours | **Impact:** ⭐⭐⭐⭐ (Massive UX improvement for demos)

---

### Feature 4.3: Multi-Model Routing with Model Specialization Display
**Pattern:** Dynamic model selection based on task type

**What it does:**
- Supervisor routes to specialists, but also **selects the optimal LLM** per task
- Code analysis → DeepSeek Coder V2
- Complex reasoning → Qwen 72B
- Fast classification → Hermes 3 8B
- Long context (log analysis) → Llama 3.1 70B
- Display which model is being used in the UI: "🤖 Using DeepSeek Coder V2 for code analysis..."

**Why this matters:** Demonstrates Featherless.ai's unique multi-model capability. This is a key differentiator since most platforms use a single model.

**Effort:** 2-3 hours (mostly routing logic + UI display) | **Impact:** ⭐⭐⭐⭐ (Showcases Featherless.ai partnership)

---

## Priority Matrix

```
                        IMPACT
                 Low ─────────── High
              ┌────────────────────────┐
         Low  │  4.3 Model    │  4.1 Memory    │
              │  Routing      │  Persistence   │
              │  (2-3h)       │  (3-4h)        │
    EFFORT    ├────────────────────────┤
              │  4.2 Streaming│  1.3 NL→SQL    │
              │  (4-6h)       │  (6-8h)        │
              │               │  2.3 1:1 Prep  │
              │               │  (4-6h)        │
              ├────────────────────────┤
         High │               │  1.1 Agentic   │
              │               │  RAG (6-8h)    │
              │               │  1.2 Fusion    │
              │               │  Retrieval     │
              │               │  (8-10h)       │
              │               │  2.1 Anomaly   │
              │               │  Detection     │
              │               │  (8-10h)       │
              │               │  3.1 Human-in  │
              │               │  -the-Loop     │
              │               │  (10-12h)      │
              │               │  3.2 CI/CD     │
              │               │  Diagnosis     │
              │               │  (8-10h)       │
              └────────────────────────┘
```

---

## Recommended Build Order (Sprint Plan)

### Day 1: Foundation + Quick Wins
| Order | Task | Hours | Cumulative |
|-------|------|-------|------------|
| 1 | **Phase 0.1**: Fix `users` → `employees` schema alignment | 1h | 1h |
| 2 | **Phase 0.2**: Build embedding generation pipeline | 3h | 4h |
| 3 | **Phase 0.3**: Seed embeddings for employees/projects | 2h | 6h |
| 4 | **Phase 0.4**: Seed ClickHouse with queryable data | 2h | 8h |
| 5 | **Feature 4.3**: Multi-model routing display | 2h | 10h |

### Day 2: Core AI Features
| Order | Task | Hours | Cumulative |
|-------|------|-------|------------|
| 6 | **Feature 1.1**: Agentic RAG with self-correction | 7h | 17h |
| 7 | **Feature 4.1**: Conversation memory | 3h | 20h |

### Day 3: Autonomous Workflows
| Order | Task | Hours | Cumulative |
|-------|------|-------|------------|
| 8 | **Feature 2.1**: Anomaly detection & alert agent | 8h | 28h |
| 9 | **Feature 2.3**: Developer 1:1 prep agent | 5h | 33h |

### Day 4: Advanced Patterns + Demo
| Order | Task | Hours | Cumulative |
|-------|------|-------|------------|
| 10 | **Feature 1.3**: NL → SQL/Cypher (uses DeepSeek) | 6h | 39h |
| 11 | **Feature 3.3**: Graph RAG expert discovery | 6h | 45h |
| 12 | **Feature 4.2**: Streaming + tool call visualization | 4h | 49h |

### Stretch Goals (if time permits)
| Order | Task | Hours |
|-------|------|-------|
| 13 | **Feature 1.2**: Multi-database fusion retrieval | 8h |
| 14 | **Feature 3.1**: Human-in-the-loop reallocation | 10h |
| 15 | **Feature 3.2**: CI/CD failure diagnosis | 8h |
| 16 | **Phase 0.5**: Neo4j graph seeding | 3h |
| 17 | **Feature 2.2**: Sprint report generator | 6h |

---

## Architecture: How Features Map to LangGraph Patterns

| Feature | LangGraph Pattern | Key Concept |
|---------|-------------------|-------------|
| 1.1 Agentic RAG | Evaluator-Optimizer Loop | Self-correction, document grading |
| 1.2 Fusion Retrieval | Orchestrator-Worker (Send API) | Parallel DB queries + synthesis |
| 1.3 NL→SQL | Prompt Chain + Conditional Edge | Query gen → validate → execute → summarize |
| 2.1 Anomaly Detection | Evaluator-Optimizer + Scheduled | Detect → investigate → alert → self-check |
| 2.2 Sprint Reports | Orchestrator-Worker (Send API) | Parallel section writing → synthesis |
| 2.3 1:1 Prep | Prompt Chain | Data gather → interpret → draft briefing |
| 3.1 Human-in-Loop | Interrupt + Checkpointer | Agent proposes → human approves → agent executes |
| 3.2 CI/CD Diagnosis | Specialized Agent + RAG | Code LLM + historical failure RAG |
| 3.3 Graph RAG | Custom Fusion Node | Vector scores + graph scores → ranked results |
| 4.1 Memory | Checkpointer | Thread-based conversation persistence |
| 4.2 Streaming | stream_mode="messages" | Real-time token + tool call streaming |
| 4.3 Multi-Model | Routing Conditional Edge | Task type → optimal model selection |

---

## Featherless.ai Model Usage Strategy

| Model | Use Cases | Features |
|-------|-----------|----------|
| **Qwen 2.5 72B** | Supervisor routing, complex reasoning, executive summaries, anomaly analysis | 1.1, 1.2, 2.1, 2.2, 2.3, 3.1 |
| **Llama 3.1 70B** | DORA analysis, long-context log analysis, historical comparison | 2.1, 3.2 |
| **Hermes 3 8B** | Fast classification (document grading, relevance scoring), parallel workers | 1.1 (grader), 2.2 (workers), 3.3 |
| **DeepSeek Coder V2** | SQL/Cypher generation, code analysis, CI/CD diagnosis, fix suggestions | 1.3, 3.2 |
| **llama-text-embed-v2** | Embedding generation for RAG pipeline | 0.2, 1.1, 1.2, 3.3 |

> **Key differentiator:** We use 5 different models, each chosen for its strengths. Most competitors use a single model for everything.

---

## What Makes This "AI" vs "CRUD"

| Old Roadmap (CRUD) | New Roadmap (AI-Native) |
|---------------------|------------------------|
| `SELECT * FROM employees WHERE workload > 80%` | LLM reasons about *why* someone is overloaded, cross-references multiple databases, and generates a reallocation plan |
| `SELECT deployment_count FROM metrics WHERE team = X` | LLM detects anomalies, hypothesizes root causes, and generates actionable alerts with recommendations |
| Text ILIKE search on content column | Cosine similarity on 1024-dim embeddings with document grading and query rewriting |
| Hardcoded synthetic data returned | Real data → LLM analysis → reasoned insights with explanations |
| Single model, single call | 5 specialized models, multi-step reasoning chains with self-correction |
| No memory between queries | Persistent conversation with context awareness |
| Agent outputs raw data | Agent outputs narrative prose, recommendations, and action plans |

---

## Technical Dependencies

### New Packages to Add
```
# requirements.txt additions
langchain-community>=0.3.0    # For embedding integrations
langgraph-checkpoint>=0.1.0   # For conversation persistence
langgraph-checkpoint-sqlite   # Or langgraph-checkpoint-postgres
```

### New Environment Variables
```
# .env additions
EMBEDDING_MODEL=llama-text-embed-v2        # Or compatible model on Featherless
EMBEDDING_DIMENSION=1024                    # Matches pgvector column
DEEPSEEK_MODEL=deepseek-ai/DeepSeek-Coder-V2-Instruct  # Already configured
```

### Key Files to Create/Modify
| File | Action | Purpose |
|------|--------|---------|
| `agents/tools/vector_tools.py` | **Rewrite** | Real cosine similarity + embedding generation |
| `agents/tools/postgres_tools.py` | **Fix** | `users` → `employees` alignment |
| `agents/tools/clickhouse_tools.py` | **Fix** | Remove hardcoded data, use real queries |
| `agents/tools/neo4j_tools.py` | **Fix** | Remove synthetic fallbacks |
| `agents/tools/action_tools.py` | **Create** | Write operations (update assignments, send notifications) |
| `agents/tools/embedding_tools.py` | **Create** | Embedding generation utilities |
| `agents/specialists/anomaly_agent.py` | **Create** | Anomaly detection specialist |
| `agents/specialists/report_agent.py` | **Create** | Sprint report generator |
| `agents/specialists/code_agent.py` | **Create** | CI/CD diagnosis with DeepSeek |
| `agents/workflows/rag_workflow.py` | **Create** | Self-reflective RAG graph |
| `agents/workflows/nl_to_query.py` | **Create** | NL→SQL/Cypher workflow |
| `scripts/seed_embeddings.py` | **Create** | Embedding generation + insertion |
| `scripts/seed_clickhouse.py` | **Create** | ClickHouse data seeding |
| `scripts/seed_neo4j.py` | **Create** | Neo4j graph seeding |

---

## Demo Script (Suggested Flow)

1. **"Show me the multi-agent system"** — Ask a question, show supervisor routing + model selection
2. **"Who can help with the payment service?"** — Agentic RAG with self-correction (grading docs, rewriting query)
3. **"Generate a weekly engineering report"** — Orchestrator-worker pattern, parallel execution, narrative synthesis
4. **"Why did deployments drop this week?"** — Anomaly detection with root cause hypothesis
5. **"Prepare me for my 1:1 with Alex tomorrow"** — 1:1 prep agent with personalized insights
6. **"What's the average velocity for teams with 5+ members?"** — NL→SQL with DeepSeek Coder V2
7. **"Compare that with last quarter"** — Conversational memory (follow-up without restating context)

---

*Document created: Feb 8, 2025*
*Replaces: `feature_implementation_roadmap.md` (CRUD-focused)*
*Status: Active POA*
