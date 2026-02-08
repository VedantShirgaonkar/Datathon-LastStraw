# Implementation Plan v2: Multi-Agent Expansion & Schema Alignment

**Objective**: Expand the Engineering Intelligence Platform to support advanced features (Voice, HR, CI/CD, Predictions) and align with the new `unified_schema.sql`.

## 1. Gap Analysis

### Feature Gaps (vs `feature_ideas.txt`)
| Feature Area | Current Status | Missing / Required |
| :--- | :--- | :--- |
| **Voice/HR Agents** | None | Agent to conduct weekly check-ins, record transcripts, and answer HR questions. |
| **CI/CD Analysis** | Basic DORA (ClickHouse) | Detailed pipeline failure analysis, "fix this error" suggestions, bottleneck detection. |
| **Alerting** | Passive (User asks) | Proactive "Push-based" alerts (e.g., mail on commit, deadline warning). |
| **Cost & Budget** | None | Budget tracking, hourly rate analysis, cost overrun alerts. |
| **Skills & Gaps** | Basic Vector Search | Explicit skill tagging, "Skill Gap" analysis for HR. |
| **Predictions** | None | Sprint completion prediction, delivery risk scoring. |

### Data Gaps (vs `unified_schema.sql` & `AI_AGENT_INTEGRATION.md`)
| Data Entity | Current (Old) | Target (`unified_schema`) | Gaps in Target |
| :--- | :--- | :--- | :--- |
| **People** | `users` | `employees` | No `hourly_rate` (Critical for cost), No `skills` column. |
| **Work** | `tasks` (Jira) | `tasks` (Unified) | Good coverage. |
| **Projects** | `projects` | `projects` | No `budget` field. |
| **CI/CD** | ClickHouse `events` | Missing in SQL | Need `ci_pipelines` tracking in SQL for operational logic (or use ClickHouse). **Ingestion Gap**: `AI_AGENT_INTEGRATION.md` does NOT show CI/CD webhooks (GitHub Actions/Jenkins). |
| **Collaboration** | Neo4j | `task_participants` | Good coverage but need to sync Neo4j logic to SQL if migrating. |

---

## 2. Proposed Agent Architecture

We will expand the **Supervisor** to route to 4 localized Specialists + 1 Background Service.

### 1. **Supervisor Agent** (Existing - Update)
*   **Role**: Router & Orchestrator.
*   **Update**: Route "HR/Voice" to Culture Agent, "CI/CD" to DevOps Agent.

### 2. **Culture & HR Agent** (New)
*   **Features**:
    *   Conducts **Voice/Text Check-ins** (Weekly updates).
    *   Analyzes **Feedback** and **Sentiment**.
    *   Identifies **Skill Gaps** (Needs `skills` data).
    *   **Inputs**: `check_ins`, `feedback`, `one_on_one_notes`, `employees`.
    *   **Voice Integration**: Processes transcripts from `agent_review_sessions`.

### 3. **DevOps & Quality Agent** (Evolution of DORA)
*   **Features**:
    *   **CI/CD Analysis**: "Why did build #42 fail?".
    *   **DORA Metrics**: Deployment freq, etc.
    *   **Tech Debt**: Tracks Code Churn/Complexity.
    *   **Inputs**: `tasks`, `task_events`, ClickHouse (`events`), *New CI/CD Tables*.

### 4. **Resource & Project Agent** (Existing - Update)
*   **Features**:
    *   **Prediction**: "Will we miss the sprint?".
    *   **Cost Analysis**: "Project X is over budget" (Needs schema update).
    *   **Allocation**: "Reassign dev from Project A to B".
    *   **Inputs**: `projects`, `project_assignments`, `employees`.

### 5. **Insights & Knowledge Agent** (Existing - Update)
*   **Features**:
    *   **Expert Finder**: "Who knows Python?".
    *   **Onboarding**: "Explain `auth_service` architecture".
    *   **Inputs**: `embeddings` (RAG), Neo4j (Collaboration).

### 6. **Sentinel Service** (New - Background)
*   **Role**: Proactive Alerting (Cron/Event-driven, not Chat-based).
*   **Features**:
    *   "Ticket done late" -> Email Manager.
    *   "Fatal Error" -> Trigger Reassignment suggestion.
    *   "Commit made" -> Mail non-tech roles.
*   **Implementation**: Scheduled Lambda/Cron searching for anomalies.

---

## 3. Database Schema Recommendations (For Teammate)

To support the above features, we need the following changes to `unified_schema.sql`:

### A. Employee Enrichment (For Resource/Cost/HR)
```sql
ALTER TABLE employees 
ADD COLUMN hourly_rate numeric(10,2), -- For Cost Analysis
ADD COLUMN skills text[],             -- For Skill Gap/Assignment (e.g. ['python', 'react'])
ADD COLUMN department text;           -- For Org Analysis
```

### B. Project Finance (For Budgeting)
```sql
ALTER TABLE projects 
ADD COLUMN budget_amount numeric(12,2),
ADD COLUMN currency text DEFAULT 'USD',
ADD COLUMN cost_to_date numeric(12,2) DEFAULT 0;
```

### C. CI/CD Pipeline Tracking (For DevOps Agent)
*Current Ingestion only covers git push/pr. We need Pipeline events.*
```sql
CREATE TABLE ci_pipelines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES projects(id),
    commit_sha text,
    status text,          -- 'success', 'failed', 'running'
    started_at timestamptz,
    finished_at timestamptz,
    error_log text,       -- Summary of error
    trigger_actor uuid REFERENCES employees(id)
);
```

### D. Notifications (For Sentinel Service)
```sql
CREATE TABLE notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id uuid REFERENCES employees(id),
    type text,            -- 'alert', 'summary', 'email'
    content text,
    status text DEFAULT 'pending', -- 'sent', 'failed'
    created_at timestamptz DEFAULT now()
);
```

---

## 4. Ingestion Layer Requests (To Teammate)

1.  **CI/CD Webhooks**: Please add **GitHub Actions** or **Jenkins** webhooks to the Ingestion API to populate `ci_pipelines`.
2.  **Schema Migration**: Apply the columns above (`hourly_rate`, `skills`, `budget`) to `unified_schema.sql`.

---

## 5. Migration Strategy for Agents

1.  **Refactor `postgres_tools.py`**:
    *   Rename query targets: `users` -> `employees`.
    *   Update join logic for `teams` and `projects`.
2.  **Create New Tools**:
    *   `get_employee_feedback`: Query `feedback` table.
    *   `log_check_in`: Insert into `check_ins`.
    *   `get_pipeline_status`: Query `ci_pipelines`.
3.  **Build New Agents**: `CultureAgent`, `DevOpsAgent`.
