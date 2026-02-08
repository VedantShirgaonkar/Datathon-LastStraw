# Engineering Intelligence Platform 🧠

> **An AI-Driven Enterprise Delivery & Workforce Intelligence System**
>
> *Transforming fragmented engineering data into actionable intelligence through autonomous agents and knowledge graphs.*

---

## 🚀 Overview

The **Engineering Intelligence Platform** bridges the gap between raw technical signals (commits, PRs, deployments) and high-level business metrics. It functions as a **"google analytics for engineering organizations"**, consuming telemetry from across the SDLC and producing executive-ready business intelligence.

By leveraging a **Supervisor Pattern** with **LangGraph** agents, we move beyond static dashboards to a system that **understands context**, **detects anomalies**, and **recommends actions**.

---

## 🏗 System Architecture

Our architecture is designed for enterprise scale, featuring a decoupled ingestion layer, event-driven processing, and a multi-model AI core.

### High-Level Architecture

The platform operates across 5 distinct layers:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ENTERPRISE INTELLIGENCE PLATFORM                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │   GitHub    │ │    Jira     │ │   Slack     │ │  Prometheus │ │   Notion    │   │
│  │    API      │ │    API      │ │    API      │ │    /metrics │ │    API      │   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │
│         │               │               │               │               │           │
│  ┌──────┴───────────────┴───────────────┴───────────────┴───────────────┴──────┐   │
│  │                        DATA INGESTION LAYER                                  │   │
│  │  • Webhooks (Real-time events)      • Polling (Historical sync)             │   │
│  └────────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                             │
│  ┌────────────────────────────────────┴─────────────────────────────────────────┐   │
│  │                     EVENT PROCESSING & ENRICHMENT                            │   │
│  │  • Decoupled Queueing (Amazon SQS)                                           │   │
│  │  • Entity Resolution (Linking GitHub User ↔ Jira User ↔ Slack ID)           │   │
│  └────────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                             │
│  ┌────────────────────────────────────┴─────────────────────────────────────────┐   │
│  │                     DATA STORAGE LAYER (Polyglot)                            │   │
│  │  • Time-Series (ClickHouse) → Metrics & Logs                                 │   │
│  │  • Vector (Pinecone) → Semantic Embeddings                                   │   │
│  │  • Graph (Neo4j Aura) → Relationships (User→Team→Project)                    │   │
│  │  • Relational (Aurora PostgreSQL) → Core Entities                            │   │
│  └────────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                             │
│  ┌────────────────────────────────────┴─────────────────────────────────────────┐   │
│  │                     AI/ML INTELLIGENCE ENGINE                                │   │
│  │  • Supervisor Agent (LangGraph Orchestrator)                                 │   │
│  │  • Specialist Agents (DORA, Resource Planning, Developer Insights)           │   │
│  │  • Multi-Model Routing (Featherless.ai)                                      │   │
│  └────────────────────────────────────┬─────────────────────────────────────────┘   │
│                                       │                                             │
│  ┌────────────────────────────────────┴─────────────────────────────────────────┐   │
│  │                     PRESENTATION LAYER                                       │   │
│  │  • Enterprise Dashboard (React)                                              │   │
│  │  • Chat Interface (Natural Language Query)                                   │   │
│  │  • Slack Bot Integration                                                     │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 AI Agent Architecture & MCP

We utilize the **Model Context Protocol (MCP)** to give our AI agents standardized access to external tools, and a **LangGraph Supervisor** to orchestrate complex reasoning.

### The Supervisor Pattern
A top-level **Supervisor Agent** (powered by **Qwen 72B**) receives user queries and routes them to specialist agents. It maintains state/memory across the conversation.

### Specialist Agents
1.  **📊 DORA Metrics Agent**:  
    *   **Goal**: Monitor Engineering Efficiency.
    *   **Data**: GitHub Commits, PRs, Deployment Events.
    *   **Output**: Deployment Frequency, Lead Time, Change Failure Rate, MTTR.

2.  **🗓 Resource Planning Agent**:  
    *   **Goal**: Predict bottlenecks and optimize staffing.
    *   **Data**: Jira Sprint Velocity, Issue Status, Calendar Availability.
    *   **Output**: "Project Alpha is at risk; suggest moving 2 devs from Project Beta."

3.  **💡 Developer Insights Agent**:  
    *   **Goal**: Understanding developer expertise and contributions.
    *   **Data**: Code diffs (languages), PR reviews (collaboration).
    *   **Output**: Automated 1:1 prep notes, skill profiling.

---

## 🧠 The Knowledge Graph & Entity Resolution

Connecting data across systems is the hardest challenge. We built an **Identity Resolution Engine** to link fragmented identities into a single `Developer` entity.

### Graph Schema (Neo4j)
*   **Nodes**: `Developer`, `Team`, `Project`, `Repository`, `Skill`, `PullRequest`, `Issue`
*   **Relationships**: 
    *   `(Developer)-[:CONTRIBUTES_TO]->(Repository)`
    *   `(Developer)-[:MEMBER_OF]->(Team)`
    *   `(Project)-[:BLOCKED_BY]->(Issue)`
    *   `(Developer)-[:HAS_SKILL]->(Skill)`

This graph enables complex questions like: *"Find a developer who knows Python, has worked on the Payment Service, and has availability next sprint."*

---

## 🎯 Hybrid RAG for Expert Discovery

We implemented a **Hybrid RAG (Retrieval-Augmented Generation)** system for HR and Resource Planning use cases.

1.  **Semantic Search**: Uses **Pinecone** to find developers based on skill descriptions (e.g., "Experience with distributed systems").
2.  **Graph Traversal**: Uses **Neo4j** to validate experience (e.g., "Must have merged PRs in `core-backend` repo").
3.  **Keyword Matching**: Filters by explicit tags (e.g., "Senior Engineer").
4.  **Reranking**: **LLM** reranks candidates based on current availability and recent project context.

---

## 🖥 Multi-Persona Enterprise Features

The platform serves different stakeholders with tailored views:

| Role | Key Insights Provided |
|------|-----------------------|
| **Engineering Lead** | Sprint Velocity, DORA Metrics, Blocker Alerts, Code Review Health. |
| **Product Manager** | Feature Delivery Prediction, Roadmap Progress, Dependency Risks. |
| **HR / People Ops** | Team Utilization, Skill Gap Analysis, Burnout Indicators, "Best Fit" Matching. |
| **Executive / CTO** | Portfolio Health, ROI Analysis, Strategic Alignment Checks. |

---

## � Tech Stack

### Core Backend & AI
*   **FastAPI**: High-performance async Python backend.
*   **LangGraph**: Stateful, cyclic agent orchestration.
*   **Featherless.ai**: Serverless inference for **Qwen 72B**, **Llama 3**, **DeepSeek Coder**.
*   **Pydantic**: Robust data validation and settings management.

### Data Layer (Polyglot Persistence)
*   **Aurora PostgreSQL (AWS)**: Core relational data (Users, Auth).
*   **ClickHouse Cloud**: OLAP database for sub-second analytics on millions of events.
*   **Neo4j Aura**: Graph database for relationship modeling.
*   **Pinecone**: Vector database for semantic search.

### Infrastructure (AWS)
*   **AWS Lambda**: Serverless compute for event ingestion and routing.
*   **Amazon SQS**: Message queue for decoupling webhooks from processing.
*   **API Gateway**: Secure entry point for all webhooks and client requests.

---

## 📄 License
MIT License. See [LICENSE](LICENSE) for more information.
