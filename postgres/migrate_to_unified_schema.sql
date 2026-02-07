-- Migration: Align with unified_schema.sql
-- From: Old schema (users, basic tables)
-- To: Unified HR Voice Agent Schema (employees, tasks, check_ins, etc.)

-- Run this migration on: engineering-intelligence1.chwmsemq65p7.ap-south-1.rds.amazonaws.com

BEGIN;

-- =============================================================================
-- STEP 1: RENAME users → employees + ADD NEW COLUMNS
-- =============================================================================

-- Rename table
ALTER TABLE IF EXISTS users RENAME TO employees;

-- Rename 'name' column to 'full_name'
ALTER TABLE employees RENAME COLUMN name TO full_name;

-- Add new columns from unified schema
ALTER TABLE employees 
    ADD COLUMN IF NOT EXISTS title text,
    ADD COLUMN IF NOT EXISTS manager_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS location text,
    ADD COLUMN IF NOT EXISTS timezone text,
    ADD COLUMN IF NOT EXISTS employment_type text,
    ADD COLUMN IF NOT EXISTS level text,
    ADD COLUMN IF NOT EXISTS start_date date,
    ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- Copy 'role' to 'title' if title is NULL (role is the old column name for job title)
UPDATE employees SET title = role WHERE title IS NULL AND role IS NOT NULL;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_employees_team_id ON employees(team_id);
CREATE INDEX IF NOT EXISTS idx_employees_manager_id ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_employees_active ON employees(active);

-- =============================================================================
-- STEP 2: UPDATE FOREIGN KEY REFERENCES (user_id → employee_id)
-- =============================================================================

-- identity_mappings: user_id → employee_id
ALTER TABLE identity_mappings RENAME COLUMN user_id TO employee_id;

-- project_assignments: user_id → employee_id  
ALTER TABLE project_assignments RENAME COLUMN user_id TO employee_id;

-- Update indexes
DROP INDEX IF EXISTS idx_identity_mappings_user;
CREATE INDEX IF NOT EXISTS idx_identity_mappings_employee ON identity_mappings(employee_id);

DROP INDEX IF EXISTS idx_project_assignments_user;
CREATE INDEX IF NOT EXISTS idx_project_assignments_employee ON project_assignments(employee_id);

-- =============================================================================
-- STEP 3: UPDATE teams TABLE
-- =============================================================================

ALTER TABLE teams 
    ADD COLUMN IF NOT EXISTS parent_team_id uuid REFERENCES teams(id) ON DELETE SET NULL;

-- =============================================================================
-- STEP 4: UPDATE projects TABLE (add budget fields per implementation plan)
-- =============================================================================

ALTER TABLE projects 
    ADD COLUMN IF NOT EXISTS budget_amount numeric(12,2),
    ADD COLUMN IF NOT EXISTS currency text DEFAULT 'USD',
    ADD COLUMN IF NOT EXISTS cost_to_date numeric(12,2) DEFAULT 0;

-- =============================================================================
-- STEP 5: ADD project_assignments ADDITIONAL COLUMNS
-- =============================================================================

ALTER TABLE project_assignments
    ADD COLUMN IF NOT EXISTS start_date date,
    ADD COLUMN IF NOT EXISTS end_date date;

-- Rename assigned_at to match schema
-- (Keep both for backwards compat)
-- ALTER TABLE project_assignments RENAME COLUMN assigned_at TO assigned_at;

-- =============================================================================
-- STEP 6: CREATE tasks TABLE (CANONICAL WORK ITEMS)
-- =============================================================================

CREATE TABLE IF NOT EXISTS tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL,
    external_key text NOT NULL,
    project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
    title text NOT NULL,
    description text,
    task_type text,
    priority text,
    status text,
    status_category text,  -- 'todo'|'in_progress'|'done'|'blocked'
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

-- =============================================================================
-- STEP 7: CREATE task_events TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    occurred_at timestamptz NOT NULL,
    event_type text NOT NULL,  -- 'status_change','comment','assignment_change','blocked','unblocked'
    from_value text,
    to_value text,
    actor_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    payload jsonb
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_time ON task_events(task_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_task_events_type_time ON task_events(event_type, occurred_at);

-- =============================================================================
-- STEP 8: CREATE task_participants TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS task_participants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    role text NOT NULL,  -- 'reviewer','collaborator','watcher'
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (task_id, employee_id, role)
);

CREATE INDEX IF NOT EXISTS idx_task_participants_employee ON task_participants(employee_id);

-- =============================================================================
-- STEP 9: CREATE check_ins TABLE (HR/VOICE AGENT)
-- =============================================================================

CREATE TABLE IF NOT EXISTS check_ins (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    cadence text NOT NULL,  -- 'weekly'|'monthly'
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

-- =============================================================================
-- STEP 10: CREATE one_on_one_notes TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS one_on_one_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    manager_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    meeting_date date NOT NULL,
    topics text,
    decisions text,
    action_items jsonb,  -- [{text, owner_employee_id, due_date, status}]
    visibility text NOT NULL DEFAULT 'private',  -- 'private'|'manager'|'hr_manager'
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_one_on_one_employee_date ON one_on_one_notes(employee_id, meeting_date);

-- =============================================================================
-- STEP 11: CREATE goals TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS goals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    period_start date NOT NULL,
    period_end date NOT NULL,
    title text NOT NULL,
    description text,
    category text,  -- 'delivery','quality','leadership','growth'
    status text DEFAULT 'active',  -- 'active','completed','cancelled'
    progress_percent numeric(5,2) DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_goals_employee_period ON goals(employee_id, period_start, period_end);

-- =============================================================================
-- STEP 12: CREATE goal_links TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS goal_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id uuid NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
    project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
    url text,
    note text
);

-- =============================================================================
-- STEP 13: CREATE feedback TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    author_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,  -- nullable for anonymous
    period_start date NOT NULL,
    period_end date NOT NULL,
    feedback_type text NOT NULL,  -- 'kudos','constructive','peer_review'
    competency text,
    rating int,
    content text NOT NULL,
    visibility text NOT NULL DEFAULT 'hr_manager',  -- 'private'|'manager'|'hr_manager'
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_subject_period ON feedback(subject_employee_id, period_start, period_end);

-- =============================================================================
-- STEP 14: CREATE employee_monthly_metrics TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS employee_monthly_metrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    month date NOT NULL,  -- store as first day of month
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

-- =============================================================================
-- STEP 15: CREATE ci_pipelines TABLE (DevOps Agent)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ci_pipelines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
    commit_sha text,
    status text,  -- 'success', 'failed', 'running'
    started_at timestamptz,
    finished_at timestamptz,
    error_log text,
    trigger_actor uuid REFERENCES employees(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ci_pipelines_project ON ci_pipelines(project_id);
CREATE INDEX IF NOT EXISTS idx_ci_pipelines_status ON ci_pipelines(status);

-- =============================================================================
-- STEP 16: CREATE notifications TABLE (Sentinel Service)
-- =============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id uuid REFERENCES employees(id) ON DELETE CASCADE,
    type text,  -- 'alert', 'summary', 'email'
    content text,
    status text DEFAULT 'pending',  -- 'sent', 'failed'
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);

-- =============================================================================
-- STEP 17: AGENT PERSONALIZATION TABLES
-- =============================================================================

CREATE TABLE IF NOT EXISTS agent_user_preferences (
    employee_id uuid PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
    preferred_summary_style text DEFAULT 'bullet',  -- 'bullet'|'narrative'
    preferred_depth text DEFAULT 'medium',  -- 'short'|'medium'|'deep'
    focus_areas text[],  -- e.g. '{delivery,collaboration,growth}'
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_review_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    reviewer_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    session_type text NOT NULL,  -- 'weekly'|'monthly'
    period_start date NOT NULL,
    period_end date NOT NULL,
    transcript text,
    summary text,
    sources_used jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_employee_period ON agent_review_sessions(employee_id, period_start, period_end);

-- =============================================================================
-- STEP 18: ACCESS CONTROL TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS data_access_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type text NOT NULL,  -- 'one_on_one_notes','feedback','check_ins','agent_review_sessions'
    resource_id uuid NOT NULL,
    principal_type text NOT NULL,  -- 'employee'|'team'|'role'
    principal_id uuid,  -- employee_id or team_id; NULL when principal_type='role'
    role text,  -- 'self'|'manager'|'hr'
    permission text NOT NULL,  -- 'read'|'write'
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policies_resource ON data_access_policies(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_policies_principal ON data_access_policies(principal_type, principal_id);

-- =============================================================================
-- STEP 19: UPDATE embeddings TABLE
-- =============================================================================

-- Update source_table values from 'users' to 'employees'
UPDATE embeddings SET source_table = 'employees' WHERE source_table = 'users';

-- Add new embedding types for new tables
COMMENT ON TABLE embeddings IS 'Embedding types: developer_profile, project_description, check_in, one_on_one, goal, feedback, documentation, code_change, issue_description, developer_activity';

-- =============================================================================
-- DONE
-- =============================================================================

COMMIT;

-- Verification queries (run after migration):
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'employees' ORDER BY ordinal_position;
