"""
Analytics Tools for Main Agent

LangChain StructuredTools that wrap the AnalyticsProcessor.
The main agent calls these to sync ClickHouse data → PostgreSQL.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from agent.analytics_processor import AnalyticsProcessor


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class SyncTasksInput(BaseModel):
    """Input for syncing Jira tasks."""
    since_hours: int = Field(default=24, description="Look back hours for events")


class SyncTaskEventsInput(BaseModel):
    """Input for syncing task status events."""
    since_hours: int = Field(default=24, description="Look back hours for events")


class SyncCIPipelinesInput(BaseModel):
    """Input for syncing CI/CD pipelines."""
    since_hours: int = Field(default=24, description="Look back hours for events")


class ComputeMetricsInput(BaseModel):
    """Input for computing monthly metrics."""
    month: Optional[str] = Field(default=None, description="Month in YYYY-MM format (default: last month)")


class FullSyncInput(BaseModel):
    """Input for full analytics sync."""
    since_hours: int = Field(default=24, description="Look back hours for events")


class GetEmployeeMetricsInput(BaseModel):
    """Input for getting employee metrics."""
    employee_email: str = Field(..., description="Employee email address")
    months: int = Field(default=3, description="Number of months to retrieve")


class GetProjectHealthInput(BaseModel):
    """Input for getting project health status."""
    project_name: str = Field(..., description="Project name or key")


# =============================================================================
# TOOL FUNCTIONS
# =============================================================================

def sync_jira_tasks(since_hours: int = 24) -> dict:
    """
    Sync Jira issues from ClickHouse to PostgreSQL tasks table.
    
    Args:
        since_hours: Look back this many hours
    
    Returns:
        dict: Sync results with task counts
    """
    processor = AnalyticsProcessor()
    try:
        return processor.sync_tasks_from_jira(since_hours)
    finally:
        processor.close()


def sync_task_events(since_hours: int = 24) -> dict:
    """
    Sync task status change events from ClickHouse to PostgreSQL.
    
    Args:
        since_hours: Look back this many hours
    
    Returns:
        dict: Sync results with event counts
    """
    processor = AnalyticsProcessor()
    try:
        return processor.sync_task_events(since_hours)
    finally:
        processor.close()


def sync_ci_pipelines(since_hours: int = 24) -> dict:
    """
    Sync GitHub Actions workflow runs to ci_pipelines table.
    
    Args:
        since_hours: Look back this many hours
    
    Returns:
        dict: Sync results with pipeline counts
    """
    processor = AnalyticsProcessor()
    try:
        return processor.sync_ci_pipelines(since_hours)
    finally:
        processor.close()


def compute_monthly_metrics(month: Optional[str] = None) -> dict:
    """
    Compute monthly performance metrics for all employees.
    
    Args:
        month: Month in YYYY-MM format (default: previous month)
    
    Returns:
        dict: Metrics computation results
    """
    processor = AnalyticsProcessor()
    try:
        return processor.compute_monthly_metrics(month)
    finally:
        processor.close()


def run_full_analytics_sync(since_hours: int = 24) -> dict:
    """
    Run full sync: tasks, task_events, participants, CI pipelines.
    
    Args:
        since_hours: Look back this many hours
    
    Returns:
        dict: Combined sync results
    """
    processor = AnalyticsProcessor()
    try:
        return processor.run_full_sync(since_hours)
    finally:
        processor.close()


def get_employee_performance_summary(employee_email: str, months: int = 3) -> dict:
    """
    Get employee performance summary with metrics.
    
    Args:
        employee_email: Employee email address
        months: Number of recent months to include
    
    Returns:
        dict: Performance summary with trends
    """
    from postgres.postgres_client import PostgresClient
    
    pg = PostgresClient()
    try:
        # Get employee
        emp = pg.execute_query(
            "SELECT id, full_name, title, team_id FROM employees WHERE email = %s",
            (employee_email,)
        )
        
        if not emp:
            return {"success": False, "message": f"Employee {employee_email} not found"}
        
        employee_id = str(emp[0]['id'])
        
        # Get metrics for last N months
        metrics = pg.execute_query("""
            SELECT month, tasks_completed, tasks_started, overdue_open,
                   blocked_items, prs_merged_count, pr_reviews_count
            FROM employee_monthly_metrics
            WHERE employee_id = %s
            ORDER BY month DESC
            LIMIT %s
        """, (employee_id, months))
        
        # Get current workload
        workload = pg.execute_query("""
            SELECT 
                COUNT(*) FILTER (WHERE status_category = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE status_category = 'todo') as todo,
                COUNT(*) FILTER (WHERE status_category = 'blocked') as blocked,
                COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status_category != 'done') as overdue
            FROM tasks
            WHERE assignee_employee_id = %s
        """, (employee_id,))
        
        return {
            "success": True,
            "employee": {
                "name": emp[0]['full_name'],
                "title": emp[0].get('title'),
                "email": employee_email
            },
            "monthly_metrics": [dict(m) for m in metrics],
            "current_workload": dict(workload[0]) if workload else {},
            "message": f"Retrieved {len(metrics)} months of metrics for {emp[0]['full_name']}"
        }
        
    finally:
        pg.close()


def get_project_health(project_name: str) -> dict:
    """
    Get project health status including tasks, CI, and team.
    
    Args:
        project_name: Project name or Jira key
    
    Returns:
        dict: Project health summary
    """
    from postgres.postgres_client import PostgresClient
    
    pg = PostgresClient()
    try:
        # Get project
        proj = pg.execute_query("""
            SELECT id, name, status, jira_project_key, github_repo
            FROM projects 
            WHERE name ILIKE %s OR jira_project_key = %s
            LIMIT 1
        """, (f"%{project_name}%", project_name))
        
        if not proj:
            return {"success": False, "message": f"Project {project_name} not found"}
        
        project_id = str(proj[0]['id'])
        
        # Task summary
        tasks = pg.execute_query("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status_category = 'done') as done,
                COUNT(*) FILTER (WHERE status_category = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE status_category = 'blocked') as blocked,
                COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status_category != 'done') as overdue
            FROM tasks
            WHERE project_id = %s AND is_deleted = false
        """, (project_id,))
        
        # Recent CI status
        ci = pg.execute_query("""
            SELECT status, COUNT(*) as cnt
            FROM ci_pipelines
            WHERE project_id = %s
            AND started_at >= NOW() - INTERVAL '7 days'
            GROUP BY status
        """, (project_id,))
        
        # Team members
        team = pg.execute_query("""
            SELECT e.full_name, e.email, pa.role
            FROM project_assignments pa
            JOIN employees e ON pa.employee_id = e.id
            WHERE pa.project_id = %s
        """, (project_id,))
        
        ci_summary = {row['status']: row['cnt'] for row in ci}
        
        return {
            "success": True,
            "project": {
                "name": proj[0]['name'],
                "status": proj[0]['status'],
                "jira_key": proj[0].get('jira_project_key'),
                "github_repo": proj[0].get('github_repo')
            },
            "task_summary": dict(tasks[0]) if tasks else {},
            "ci_last_7_days": ci_summary,
            "team": [{"name": t['full_name'], "role": t['role']} for t in team],
            "message": f"Project {proj[0]['name']} health retrieved"
        }
        
    finally:
        pg.close()


# =============================================================================
# LANGCHAIN STRUCTURED TOOLS
# =============================================================================

analytics_tools = [
    StructuredTool.from_function(
        func=sync_jira_tasks,
        name="sync_jira_tasks",
        description="Sync Jira issues from ClickHouse raw events to PostgreSQL tasks table. Call when you need fresh task data.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=sync_task_events,
        name="sync_task_events",
        description="Sync task status change events to PostgreSQL. Tracks task transitions (todo→in_progress→done).",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=sync_ci_pipelines,
        name="sync_ci_pipelines",
        description="Sync GitHub Actions/CI pipeline runs from ClickHouse to PostgreSQL ci_pipelines table.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=compute_monthly_metrics,
        name="compute_monthly_metrics",
        description="Compute monthly performance metrics for all employees. Aggregates tasks, PRs, reviews.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=run_full_analytics_sync,
        name="run_full_analytics_sync",
        description="Run complete analytics sync: tasks, events, participants, CI pipelines. Use for comprehensive refresh.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_employee_performance_summary,
        name="get_employee_performance_summary",
        description="Get employee performance summary with monthly metrics and current workload. Use for HR reviews.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_project_health,
        name="get_project_health",
        description="Get project health status including task breakdown, CI status, and team. Use for project reviews.",
        return_direct=False
    ),
]
