# Feature Implementation Roadmap & POA

**Objective**: A step-by-step Plan of Action (POA) to implement "Standout" Enterprise Features, prioritized by data availability and impact.

## 🔴 Critical Prerequisite: Agent Refactoring
*Before building ANY new features, we must fix the existing tools to work with the new schema.*
*   **Action**: Update `postgres_tools.py` to use `employees` instead of `users`.
*   **Database**: PostgreSQL.
*   **Status**: 🚨 **Blocker** (Must be done first).

---

## 📅 Phase 1: The "Manager's Superpower" (Immediate Impact)
*Goal: Give leadership high-level visibility into money and productivity.*

| Priority | Feature Name | Description | Databases & Tables |
| :--- | :--- | :--- | :--- |
| **1.1** | **Weekly Leadership Summaries** | AI generates a natural language report: "Team X shipped 5 tickets but mostly bug fixes." | **Postgres**: `tasks`, `projects`<br>**ClickHouse**: `events` (commits) |
| **1.2** | **Resource & Cost Analysis** | Calculate real-time burn rate. "Project Alpha cost $15k this week." (Hours * Hourly Rate). | **Postgres**: `employees` (`hourly_rate`), `tasks` (`hours_spent`), `projects` (`budget`) |
| **1.3** | **Workforce Utilization** | Identifies overloaded vs. idle devs. "Alice has 5 active tasks, Bob has 0." | **Postgres**: `project_assignments`, `tasks` (`status='IN_PROGRESS'`) |

---

## 🛡️ Phase 2: The "Risk Guardian" (Proactive & AI)
*Goal: Catch problems before they become fires.*

| Priority | Feature Name | Description | Databases & Tables |
| :--- | :--- | :--- | :--- |
| **2.1** | **Ghost Work Alert** | Detects devs coding without tickets. "Rahul committed 500 lines but has no Jira ticket." | **ClickHouse**: `events` (commits)<br>**Postgres**: `tasks` (tickets) |
| **2.2** | **Sprint Risk Scoring** | "Sprint 24 is at Risk." predicts completion chance based on historical velocity. | **ClickHouse**: `dora_daily_metrics` (velocity)<br>**Postgres**: `tasks` (due dates) |
| **2.3** | **Bus Factor Alert** | "Only Vedant knows the Billing Service." Identifies single points of failure. | **Neo4j**: `Developer`-`[CONTRIBUTED_TO]`->`Project` |

---

## 🧠 Phase 3: The "Engineering Brain" (Graph & Complex Logic)
*Goal: Optimize the organization using relationships.*

| Priority | Feature Name | Description | Databases & Tables |
| :--- | :--- | :--- | :--- |
| **3.1** | **Intelligent Reallocation** | "Move Sarah to Backend; she knows Python and has capacity." | **Neo4j**: `Skill` graph<br>**Postgres**: `employees` (dept), `project_assignments` |
| **3.2** | **Cross-Team Collab Map** | Visualizes silos. "Why is Frontend isolated from API team?" | **Neo4j**: `Developer`-`[COLLABORATES_WITH]`->`Developer` |
| **3.3** | **Expert Finder** | "Who can help me with the Stripe Integration?" | **Neo4j**: `Developer`-`[EXPERT_IN]`->`Topic` |

---

## 🚧 Phase 4: The "DevOps Healer" (Blocked - Needs Data)
*Goal: Fix broken builds and technical debt.*
*Note: We need to ingest data into `ci_pipelines` before these work.*

| Priority | Feature Name | Description | Databases & Tables |
| :--- | :--- | :--- | :--- |
| **4.1** | **Pipeline Failure Analysis** | "Build #404 failed due to Docker OOM." | **Postgres**: `ci_pipelines` (Empty ❌) |
| **4.2** | **Change Failure Rate** | % of deploys that cause incidents. | **Postgres**: `ci_pipelines`<br>**ClickHouse**: `events` (incidents) |
| **4.3** | **Technical Debt Tracker** | Tracks code churn vs. refactoring. | **ClickHouse**: `events` (churn metrics) |

---

## Implementation Strategy (How we will build them)

1.  **Refactor Tools**: Fix `postgres_tools.py` immediately.
2.  **Build Phase 1 Agents**:
    *   Update `ResourceAgent` to read `hourly_rate`.
    *   Create `ReportingAgent` for Weekly Summaries.
3.  **Build Phase 2 Agents**:
    *   Create `SentinelService` (Background) for Ghost Work.
    *   Update `ResourceAgent` for Risk Scoring.
4.  **Build Phase 3 Agents**:
    *   Update `InsightsAgent` to use full Neo4j capabilities.
