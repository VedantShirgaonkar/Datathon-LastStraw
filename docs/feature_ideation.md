# Feature Ideation & Architecture Plan: Engineering Intelligence Platform 2.0

**Objective**: Define a "Standout" feature set for Large-Scale Enterprise usability, categorized by Active vs. Passive execution and Agent Architecture.

## 1. Core Philosophy: "From Dashboard to Copilot"
Most platforms (LinearB, Jellyfish) are **passive dashboards**. To stand out, this platform must be **active**: it shouldn't just *show* problems; it should *fix* them or *force* decisions.

---

## 2. Feature Category 1: The "Sentinel" Layer (Passive / Monitoring)
*These features run constantly in the background, ingesting data streams (Kafka) and updating the "World State".*

| Feature Name | Enterprise Value | Implementation |
| :--- | :--- | :--- |
| **Shadow Work Detection** | Identifies "Ghost Work" (Commits without Tickets). Enterprises lose 20-30% capacity here. | **Tool**: Git/Jira Correlator. <br> **Architecture**: Stream Processor (Lambda) -> Update `metrics`. |
| **Investment Profile (Capex/Opex)** | Automates R&D tax capitalization artifacts. Classifies work as "New Feature", "Maintenance", or "KTLO". | **Tool**: NLP Classifier on Ticket Titles. <br> **Architecture**: Background Job. |
| **Meeting vs. Maker Time** | Correlates Calendar (GCal) with Git activity to measure "Context Switching Cost". | **Tool**: Calendar API Integration. <br> **Architecture**: Data Pipeline. |
| **Skill DNA Graph** | Dynamically builds "Developer Resumes" based on actual code committed (e.g., "Maintains Anthropic API integration"). | **Tool**: Neo4j Graph Builder. <br> **Architecture**: Vector Embedding pipeline. |

---

## 3. Feature Category 2: The "Overseer" Agents (Active / Proactive)
*These agents autonomously wake up based on triggers (Time, Event, Risk Threshold) to act.*

| Feature Name | Action / Behavior | Architecture |
| :--- | :--- | :--- |
| **Calendar Defender Agent** | **Trigger**: Dev has < 2hr active coding blocks.<br>**Action**: Autoschedules "Focus Time" on calendar or declines non-critical meetings. | **Architecture**: Isolated Agent (Cron-based). |
| **Sprint Rescue Agent** | **Trigger**: Sprint Completion Probability < 60%.<br>**Action**: Proposes specific scope cuts to the Manager via Slack. "Drop Ticket-123 to save the Sprint goal." | **Architecture**: Specialized "RiskAgent". |
| **Budget Warlord** | **Trigger**: Cloud/Resource cost exceeds run rate.<br>**Action**: Alerts VP with "Project X is bleeding money. Root cause: API Gateway deployment." | **Architecture**: Specialized "ResourceAgent" + Cost API. |
| **PR Unblocker** | **Trigger**: PR stale for > 24hrs.<br>**Action**: Finds the *best* reviewer (based on availability & context) and slacks them: "Hey, can you unblock this? I know you worked on this module last week." | **Architecture**: "devOpsAgent" + Collaboration Graph. |

---

## 4. Feature Category 3: The "Oracle" Interface (Interactive / Multi-Agent)
*The Chat interface for complex reasoning.*

| Feature Name | Enterprise Use Case | Architecture |
| :--- | :--- | :--- |
| **"What-If" Simulator** | User: "If we move Team A to Project B, how does that affect the deadline?"<br>System: Simulates velocity change based on Team A's historical ramp-up time. | **Architecture**: Supervisor -> ResourcePlanner (Simulation Mode). |
| **Knowledge Onboarding** | User: "I'm new to the Auth Service. Walk me through the code and recent bugs."<br>System: VR/Interactive walkthrough using Embeddings + Code Graph. | **Architecture**: InsightsAgent (RAG). |
| **Performance Context** | Manager: "Write a performance review for Alice."<br>System: Drafts checking based on *Committed Code*, *PR Reviews Done*, and *Complexity Handled* (not just hours). | **Architecture**: Supervisor -> CultureAgent. |

---

## 5. Architectural Blueprint for Scale

To support "Enterprise Scale", we must move beyond a single Monolith Agent.

### A. The "Hive" Architecture
*   **Router (Supervisor)**: The existing user-facing entry point.
*   **Worker Bees (Specialists)**:
    *   `DevOpsAgent` (Tools: Jenkins, GitHub, AWS)
    *   `PeopleAgent` (Tools: Workday/HRIS, Calendar, Slack)
    *   `FinanceAgent` (Tools: CloudWatch Cost, Jira Estimates)
*   **The "Lobe" (Shared Memory)**:
    *   **Postgres**: Structured Data (Transactions).
    *   **Neo4j**: Relationship Data (Who knows what?).
    *   **VectorDB**: Semantic Data (What does this code do?).

### B. Toggle-Based Autonomy
Enterprises hate "Black Boxes". Every Agent must have **Autonomy Levels**:
1.  **Advisor (Level 1)**: Suggests action to user. (Default)
2.  **Copilot (Level 2)**: Drafts action, waits for approval.
3.  **Autopilot (Level 3)**: Executes and notifies.

*Example*: The **Calendar Defender** starts at Level 1 ("You should block time"), moves to Level 2 ("I drafted a block, click to confirm"), and eventually Level 3 ("I declined 3 meetings").

---

## 6. Recommended "Standout" MVP Features
For this project, prioritizing the highest "Wow Factor":

1.  **Voice-First Daily Standup (Passive -> Active)**
    *   *Dev speaks to Mobile App*: "I fixed the login bug but the API is flaky."
    *   *Agent*: Updates Jira status, adds comment "API flaky", and Slacks the API team.
2.  **The "Bus Factor" Alert (Active)**
    *   *Agent*: "Critical Risk: Only `vedant` knows the `billing-service`. If he leaves, we are blocked. Suggest pairing him with `rahul` next sprint."
3.  **Cost-Per-Feature Analysis (Passive)**
    *   *Agent*: "Feature `Dark Mode` cost $15,000 in dev time but is only used by 1% of users." (Combines Analytics + Jira).
