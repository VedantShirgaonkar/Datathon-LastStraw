-- Unified HR Voice Agent Schema (PostgreSQL)
-- Goal: Highly personalized monthly HR reviews grounded in work evidence + employee narrative.
-- Requires extensions:
--   - pgcrypto for gen_random_uuid()
--   - vector (pgvector) only if you use embeddings

CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- 1) ORG + IDENTITY
-- =========================

CREATE TABLE IF NOT EXISTS teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  parent_team_id uuid REFERENCES teams(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  full_name text NOT NULL,
  title text,
  team_id uuid REFERENCES teams(id) ON DELETE SET NULL,
  manager_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  location text,
  timezone text,
  employment_type text,
  level text,
  start_date date,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employees_team_id ON employees(team_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager_id ON employees(manager_id);

-- Maps each employee to external identities (Jira/GitHub/Slack/Notion/etc.)
CREATE TABLE IF NOT EXISTS identity_mappings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  source text NOT NULL,
  external_id text NOT NULL,
  external_username text,
  external_email text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_identity_mappings_employee ON identity_mappings(employee_id);
CREATE INDEX IF NOT EXISTS idx_identity_mappings_source_username ON identity_mappings(source, external_username);

-- =========================
-- 2) PROJECTS + ASSIGNMENTS
-- =========================

CREATE TABLE IF NOT EXISTS projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  github_repo text,
  jira_project_key text,
  notion_database_id text,
  status text DEFAULT 'active',
  priority text DEFAULT 'medium',
  target_date date,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS project_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role text DEFAULT 'contributor',
  allocated_percent numeric(5,2) DEFAULT 100.00,
  start_date date,
  end_date date,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_id, project_id, start_date)
);

CREATE INDEX IF NOT EXISTS idx_project_assignments_employee ON project_assignments(employee_id);
CREATE INDEX IF NOT EXISTS idx_project_assignments_project ON project_assignments(project_id);

-- =========================
-- 3) TASKS (CANONICAL WORK ITEMS)
-- =========================

-- Canonical task entity (typically Jira issue; can also represent Notion items).
CREATE TABLE IF NOT EXISTS tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  source text NOT NULL,                 -- 'jira','notion','internal'
  external_key text NOT NULL,           -- e.g. 'APIGW-123' or notion page id

  project_id uuid REFERENCES projects(id) ON DELETE SET NULL,

  title text NOT NULL,
  description text,

  task_type text,
  priority text,

  -- Normalized status fields (drive consistent HR summaries)
  status text,
  status_category text,                 -- 'todo'|'in_progress'|'done'|'blocked'

  created_at_source timestamptz,
  updated_at_source timestamptz,
  due_date date,

  reporter_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  assignee_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,

  estimate_points numeric(6,2),
  original_estimate_hours numeric(8,2),
  remaining_estimate_hours numeric(8,2),

  labels text[],
  metadata jsonb,

  is_deleted boolean NOT NULL DEFAULT false,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  UNIQUE (source, external_key)
);

CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_employee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status_cat ON tasks(status_category);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_source ON tasks(updated_at_source);

-- Task timeline/events (status changes, comments, reassignment, blockers, etc.)
CREATE TABLE IF NOT EXISTS task_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  occurred_at timestamptz NOT NULL,
  event_type text NOT NULL,             -- 'status_change','comment','assignment_change','blocked','unblocked','field_change'
  from_value text,
  to_value text,
  actor_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  payload jsonb
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_time ON task_events(task_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_task_events_type_time ON task_events(event_type, occurred_at);

-- Collaborators / reviewers / watchers
CREATE TABLE IF NOT EXISTS task_participants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  role text NOT NULL,                   -- 'reviewer','collaborator','watcher'
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (task_id, employee_id, role)
);

CREATE INDEX IF NOT EXISTS idx_task_participants_employee ON task_participants(employee_id);

-- =========================
-- 4) EMPLOYEE NARRATIVE (HIGH PERSONALIZATION)
-- =========================

-- Employee check-ins (weekly/monthly). Key source for personalized HR review context.
CREATE TABLE IF NOT EXISTS check_ins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  cadence text NOT NULL,                -- 'weekly'|'monthly'
  period_start date NOT NULL,
  period_end date NOT NULL,
  wins text,
  challenges text,
  blockers text,
  learnings text,
  next_period_focus text,
  help_needed text,
  morale_score int,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_id, cadence, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_check_ins_employee_period ON check_ins(employee_id, period_start, period_end);

-- 1:1 notes (highly sensitive; keep strict access control via policies below)
CREATE TABLE IF NOT EXISTS one_on_one_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  manager_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  meeting_date date NOT NULL,
  topics text,
  decisions text,
  action_items jsonb,                   -- [{text, owner_employee_id, due_date, status}]
  visibility text NOT NULL DEFAULT 'private', -- 'private'|'manager'|'hr_manager'
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_one_on_one_employee_date ON one_on_one_notes(employee_id, meeting_date);

-- Goals / OKRs (growth + performance)
CREATE TABLE IF NOT EXISTS goals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  period_start date NOT NULL,
  period_end date NOT NULL,
  title text NOT NULL,
  description text,
  category text,                        -- 'delivery','quality','leadership','growth'
  status text DEFAULT 'active',         -- 'active','completed','cancelled'
  progress_percent numeric(5,2) DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_goals_employee_period ON goals(employee_id, period_start, period_end);

CREATE TABLE IF NOT EXISTS goal_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id uuid NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
  task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
  project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
  url text,
  note text
);

-- Peer/manager feedback (360)
CREATE TABLE IF NOT EXISTS feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  author_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL, -- nullable for anonymous
  period_start date NOT NULL,
  period_end date NOT NULL,
  feedback_type text NOT NULL,          -- 'kudos','constructive','peer_review'
  competency text,
  rating int,
  content text NOT NULL,
  visibility text NOT NULL DEFAULT 'hr_manager', -- 'private'|'manager'|'hr_manager'
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_subject_period ON feedback(subject_employee_id, period_start, period_end);

-- =========================
-- 5) METRICS (COMPUTED/DERIVED)
-- =========================

-- Monthly rollups per employee (materialized by your pipeline/job)
CREATE TABLE IF NOT EXISTS employee_monthly_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  month date NOT NULL,                  -- store as first day of month

  tasks_completed int DEFAULT 0,
  tasks_started int DEFAULT 0,
  overdue_open int DEFAULT 0,
  blocked_items int DEFAULT 0,

  cycle_time_p50_hours numeric(10,2),
  cycle_time_p90_hours numeric(10,2),

  prs_merged_count int DEFAULT 0,
  pr_reviews_count int DEFAULT 0,

  incidents int DEFAULT 0,
  escalations int DEFAULT 0,

  generated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_id, month)
);

CREATE INDEX IF NOT EXISTS idx_employee_monthly_metrics_employee_month ON employee_monthly_metrics(employee_id, month);

-- =========================
-- 6) EMBEDDINGS (OPTIONAL: RAG MEMORY)
-- =========================

-- If you enable pgvector, you can store embeddings locally.
-- If you use Pinecone instead, you can skip this and store references only.
CREATE TABLE IF NOT EXISTS embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  embedding_type text NOT NULL,         -- 'check_in','one_on_one','goal','doc','feedback'
  source_id uuid,
  source_table text,
  -- embedding vector(1536),
  title text,
  content text,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings(embedding_type);

-- =========================
-- 7) AGENT PERSONALIZATION + AUDIT
-- =========================

CREATE TABLE IF NOT EXISTS agent_user_preferences (
  employee_id uuid PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
  preferred_summary_style text DEFAULT 'bullet',   -- 'bullet'|'narrative'
  preferred_depth text DEFAULT 'medium',           -- 'short'|'medium'|'deep'
  focus_areas text[],                              -- e.g. '{delivery,collaboration,growth}'
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_review_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  reviewer_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  session_type text NOT NULL,                      -- 'weekly'|'monthly'
  period_start date NOT NULL,
  period_end date NOT NULL,
  transcript text,
  summary text,
  sources_used jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_employee_period ON agent_review_sessions(employee_id, period_start, period_end);

-- =========================
-- 8) PRIVACY / ACCESS CONTROL
-- =========================

-- Keep it simple: row-level access grants for sensitive resources.
CREATE TABLE IF NOT EXISTS data_access_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type text NOT NULL,         -- 'one_on_one_notes','feedback','check_ins','agent_review_sessions'
  resource_id uuid NOT NULL,
  principal_type text NOT NULL,        -- 'employee'|'team'|'role'
  principal_id uuid,                   -- employee_id or team_id; NULL when principal_type='role'
  role text,                           -- 'self'|'manager'|'hr'
  permission text NOT NULL,            -- 'read'|'write'
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policies_resource ON data_access_policies(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_policies_principal ON data_access_policies(principal_type, principal_id);
