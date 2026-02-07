"""
Analytics Processor Agent

Reads raw events from ClickHouse and populates structured PostgreSQL tables.
This runs separately from the main agent to process historical/batch data.

Tables populated:
- tasks: From Jira issue events
- task_events: From Jira status changes
- task_participants: From PR reviewers/collaborators
- ci_pipelines: From GitHub workflow_run events
- employee_monthly_metrics: Aggregated rollup from all events

The main agent calls these as tools for on-demand sync.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID
import json

from clickhouse.clickhouse_client import ClickHouseClient
from postgres.postgres_client import PostgresClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalyticsProcessor:
    """
    Processes ClickHouse events and syncs to PostgreSQL structured tables.
    """
    
    def __init__(self):
        self.ch_client = ClickHouseClient()
        self.pg_client = PostgresClient()
        logger.info("Analytics Processor initialized")
    
    def close(self):
        self.ch_client.close()
        self.pg_client.close()
    
    # =========================================================================
    # TASK SYNC (Jira Issues → tasks table)
    # =========================================================================
    
    def sync_tasks_from_jira(self, since_hours: int = 24) -> Dict[str, Any]:
        """
        Sync Jira issues to tasks table.
        
        Args:
            since_hours: Look back this many hours for events
        
        Returns:
            dict: Sync results with counts
        """
        logger.info(f"Syncing tasks from Jira events (last {since_hours}h)")
        
        # Get Jira issue events from ClickHouse
        query = """
            SELECT 
                entity_id,
                actor_id,
                project_id,
                metadata,
                timestamp,
                event_type
            FROM events
            WHERE source = 'jira'
            AND event_type IN ('issue_created', 'issue_updated', 'issue_completed')
            AND timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp ASC
        """.format(hours=since_hours)
        
        events = self.ch_client.query(query)
        
        created = 0
        updated = 0
        errors = []
        
        for event in events:
            try:
                metadata = json.loads(event['metadata']) if isinstance(event['metadata'], str) else event['metadata']
                
                # Map Jira fields to task schema
                external_key = event['entity_id']  # e.g., "PROJ-123"
                
                # Check if task exists
                existing = self.pg_client.execute_query(
                    "SELECT id FROM tasks WHERE source = 'jira' AND external_key = %s",
                    (external_key,)
                )
                
                # Map status to status_category
                status = metadata.get('status', 'To Do')
                status_category = self._map_jira_status(status)
                
                # Resolve assignee employee_id from identity_mappings
                assignee_id = self._resolve_employee_id('jira', event['actor_id'])
                reporter_id = self._resolve_employee_id('jira', metadata.get('reporter'))
                project_uuid = self._resolve_project_id(event['project_id'])
                
                if existing:
                    # Update existing task
                    self.pg_client.execute_write("""
                        UPDATE tasks SET
                            title = %s,
                            description = %s,
                            status = %s,
                            status_category = %s,
                            priority = %s,
                            assignee_employee_id = %s,
                            updated_at_source = %s,
                            due_date = %s,
                            estimate_points = %s,
                            labels = %s,
                            metadata = %s,
                            updated_at = NOW()
                        WHERE source = 'jira' AND external_key = %s
                    """, (
                        metadata.get('summary', metadata.get('title', '')),
                        metadata.get('description'),
                        status,
                        status_category,
                        metadata.get('priority', 'Medium'),
                        assignee_id,
                        event['timestamp'],
                        metadata.get('due_date'),
                        metadata.get('story_points'),
                        metadata.get('labels', []),
                        json.dumps(metadata),
                        external_key
                    ))
                    updated += 1
                else:
                    # Insert new task
                    self.pg_client.execute_write("""
                        INSERT INTO tasks (
                            source, external_key, project_id, title, description,
                            task_type, priority, status, status_category,
                            created_at_source, updated_at_source, due_date,
                            reporter_employee_id, assignee_employee_id,
                            estimate_points, labels, metadata
                        ) VALUES (
                            'jira', %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s
                        )
                    """, (
                        external_key,
                        project_uuid,
                        metadata.get('summary', metadata.get('title', '')),
                        metadata.get('description'),
                        metadata.get('issuetype', 'Task'),
                        metadata.get('priority', 'Medium'),
                        status,
                        status_category,
                        event['timestamp'],
                        event['timestamp'],
                        metadata.get('due_date'),
                        reporter_id,
                        assignee_id,
                        metadata.get('story_points'),
                        metadata.get('labels', []),
                        json.dumps(metadata)
                    ))
                    created += 1
                    
            except Exception as e:
                errors.append(f"{event['entity_id']}: {str(e)}")
                logger.error(f"Error syncing task {event['entity_id']}: {e}")
        
        return {
            "success": True,
            "tasks_created": created,
            "tasks_updated": updated,
            "errors": errors[:10],  # Limit error list
            "message": f"Synced {created} new, {updated} updated tasks from Jira"
        }
    
    def _map_jira_status(self, status: str) -> str:
        """Map Jira status to normalized status_category."""
        status_lower = status.lower()
        if status_lower in ['to do', 'open', 'backlog', 'new']:
            return 'todo'
        elif status_lower in ['in progress', 'in development', 'in review', 'code review']:
            return 'in_progress'
        elif status_lower in ['done', 'closed', 'resolved', 'completed']:
            return 'done'
        elif status_lower in ['blocked', 'on hold', 'waiting']:
            return 'blocked'
        return 'todo'
    
    # =========================================================================
    # TASK EVENTS SYNC (Status changes → task_events table)
    # =========================================================================
    
    def sync_task_events(self, since_hours: int = 24) -> Dict[str, Any]:
        """
        Sync Jira status transition events to task_events table.
        """
        logger.info(f"Syncing task events (last {since_hours}h)")
        
        query = """
            SELECT 
                entity_id,
                actor_id,
                metadata,
                timestamp,
                event_type
            FROM events
            WHERE source = 'jira'
            AND event_type = 'issue_updated'
            AND JSONExtractString(metadata, 'status_from') != ''
            AND timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp ASC
        """.format(hours=since_hours)
        
        events = self.ch_client.query(query)
        
        inserted = 0
        errors = []
        
        for event in events:
            try:
                metadata = json.loads(event['metadata']) if isinstance(event['metadata'], str) else event['metadata']
                
                # Get task UUID
                task = self.pg_client.execute_query(
                    "SELECT id FROM tasks WHERE source = 'jira' AND external_key = %s",
                    (event['entity_id'],)
                )
                
                if not task:
                    continue
                
                task_id = task[0]['id']
                actor_id = self._resolve_employee_id('jira', event['actor_id'])
                
                # Check for duplicate event
                existing = self.pg_client.execute_query("""
                    SELECT id FROM task_events 
                    WHERE task_id = %s AND occurred_at = %s AND event_type = 'status_change'
                """, (str(task_id), event['timestamp']))
                
                if existing:
                    continue
                
                # Insert task event
                self.pg_client.execute_write("""
                    INSERT INTO task_events (
                        task_id, occurred_at, event_type, from_value, to_value,
                        actor_employee_id, payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(task_id),
                    event['timestamp'],
                    'status_change',
                    metadata.get('status_from'),
                    metadata.get('status_to'),
                    actor_id,
                    json.dumps(metadata)
                ))
                inserted += 1
                
            except Exception as e:
                errors.append(f"{event['entity_id']}: {str(e)}")
        
        return {
            "success": True,
            "events_inserted": inserted,
            "errors": errors[:10],
            "message": f"Synced {inserted} task events"
        }
    
    # =========================================================================
    # TASK PARTICIPANTS SYNC (PR reviewers → task_participants table)
    # =========================================================================
    
    def sync_task_participants(self, since_hours: int = 24) -> Dict[str, Any]:
        """
        Sync PR reviewers and collaborators to task_participants table.
        """
        logger.info(f"Syncing task participants (last {since_hours}h)")
        
        query = """
            SELECT 
                entity_id,
                actor_id,
                metadata,
                timestamp
            FROM events
            WHERE source = 'github'
            AND event_type = 'pr_reviewed'
            AND timestamp >= now() - INTERVAL {hours} HOUR
        """.format(hours=since_hours)
        
        events = self.ch_client.query(query)
        
        inserted = 0
        
        for event in events:
            try:
                metadata = json.loads(event['metadata']) if isinstance(event['metadata'], str) else event['metadata']
                
                # Try to find linked task (by PR title or branch name containing issue key)
                pr_title = metadata.get('pr_title', '')
                pr_branch = metadata.get('branch', '')
                
                # Extract issue key from branch (e.g., "feature/PROJ-123-description")
                import re
                issue_match = re.search(r'([A-Z]+-\d+)', pr_title + ' ' + pr_branch)
                
                if not issue_match:
                    continue
                
                issue_key = issue_match.group(1)
                
                # Get task
                task = self.pg_client.execute_query(
                    "SELECT id FROM tasks WHERE external_key = %s",
                    (issue_key,)
                )
                
                if not task:
                    continue
                
                task_id = task[0]['id']
                reviewer_id = self._resolve_employee_id('github', event['actor_id'])
                
                if not reviewer_id:
                    continue
                
                # Upsert participant
                self.pg_client.execute_write("""
                    INSERT INTO task_participants (task_id, employee_id, role)
                    VALUES (%s, %s, 'reviewer')
                    ON CONFLICT (task_id, employee_id, role) DO NOTHING
                """, (str(task_id), reviewer_id))
                inserted += 1
                
            except Exception as e:
                logger.error(f"Error syncing participant: {e}")
        
        return {
            "success": True,
            "participants_added": inserted,
            "message": f"Added {inserted} task participants"
        }
    
    # =========================================================================
    # CI PIPELINES SYNC (GitHub workflow_run → ci_pipelines table)
    # =========================================================================
    
    def sync_ci_pipelines(self, since_hours: int = 24) -> Dict[str, Any]:
        """
        Sync GitHub Actions workflow runs to ci_pipelines table.
        """
        logger.info(f"Syncing CI pipelines (last {since_hours}h)")
        
        query = """
            SELECT 
                entity_id,
                actor_id,
                project_id,
                metadata,
                timestamp
            FROM events
            WHERE source = 'github'
            AND event_type IN ('workflow_run', 'deployment')
            AND timestamp >= now() - INTERVAL {hours} HOUR
            ORDER BY timestamp ASC
        """.format(hours=since_hours)
        
        events = self.ch_client.query(query)
        
        inserted = 0
        updated = 0
        
        for event in events:
            try:
                metadata = json.loads(event['metadata']) if isinstance(event['metadata'], str) else event['metadata']
                
                commit_sha = metadata.get('commit_sha', metadata.get('sha', ''))[:40]
                status = metadata.get('conclusion', metadata.get('status', 'unknown'))
                
                project_uuid = self._resolve_project_id(event['project_id'])
                trigger_actor = self._resolve_employee_id('github', event['actor_id'])
                
                # Check existing by commit_sha + project
                existing = self.pg_client.execute_query("""
                    SELECT id FROM ci_pipelines 
                    WHERE commit_sha = %s AND project_id = %s
                """, (commit_sha, project_uuid))
                
                if existing:
                    # Update status
                    self.pg_client.execute_write("""
                        UPDATE ci_pipelines SET
                            status = %s,
                            finished_at = %s,
                            error_log = %s
                        WHERE commit_sha = %s AND project_id = %s
                    """, (
                        status,
                        event['timestamp'] if status in ['success', 'failure'] else None,
                        metadata.get('error_message') if status == 'failure' else None,
                        commit_sha,
                        project_uuid
                    ))
                    updated += 1
                else:
                    # Insert new pipeline
                    self.pg_client.execute_write("""
                        INSERT INTO ci_pipelines (
                            project_id, commit_sha, status, started_at, finished_at,
                            error_log, trigger_actor
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        project_uuid,
                        commit_sha,
                        status,
                        event['timestamp'],
                        event['timestamp'] if status in ['success', 'failure'] else None,
                        metadata.get('error_message') if status == 'failure' else None,
                        trigger_actor
                    ))
                    inserted += 1
                    
            except Exception as e:
                logger.error(f"Error syncing CI pipeline: {e}")
        
        return {
            "success": True,
            "pipelines_created": inserted,
            "pipelines_updated": updated,
            "message": f"Synced {inserted} new, {updated} updated CI pipelines"
        }
    
    # =========================================================================
    # MONTHLY METRICS ROLLUP
    # =========================================================================
    
    def compute_monthly_metrics(self, month: Optional[str] = None) -> Dict[str, Any]:
        """
        Compute monthly metrics for all employees.
        
        Args:
            month: Month in YYYY-MM format (default: previous month)
        """
        if not month:
            # Default to previous month
            today = datetime.now()
            first_of_month = today.replace(day=1)
            last_month = first_of_month - timedelta(days=1)
            month = last_month.strftime('%Y-%m')
        
        month_start = f"{month}-01"
        # Calculate month end
        year, mon = map(int, month.split('-'))
        if mon == 12:
            month_end = f"{year + 1}-01-01"
        else:
            month_end = f"{year}-{mon + 1:02d}-01"
        
        logger.info(f"Computing monthly metrics for {month}")
        
        # Get all employees
        employees = self.pg_client.execute_query("SELECT id, email FROM employees WHERE active = true")
        
        metrics_updated = 0
        
        for emp in employees:
            employee_id = str(emp['id'])
            
            # Get identity mappings for this employee
            identities = self.pg_client.execute_query("""
                SELECT source, external_id, external_username 
                FROM identity_mappings WHERE employee_id = %s
            """, (employee_id,))
            
            # Build actor_ids list for ClickHouse query
            actor_ids = [emp['email']]
            for identity in identities:
                if identity['external_id']:
                    actor_ids.append(identity['external_id'])
                if identity['external_username']:
                    actor_ids.append(identity['external_username'])
            
            # Query ClickHouse for this employee's activity
            actor_list = "'" + "','".join(actor_ids) + "'"
            
            metrics_query = f"""
                SELECT
                    countIf(source = 'jira' AND event_type = 'issue_completed') as tasks_completed,
                    countIf(source = 'jira' AND event_type = 'issue_created') as tasks_started,
                    countIf(source = 'github' AND event_type = 'pr_merged') as prs_merged,
                    countIf(source = 'github' AND event_type = 'pr_reviewed') as pr_reviews
                FROM events
                WHERE actor_id IN ({actor_list})
                AND timestamp >= '{month_start}'
                AND timestamp < '{month_end}'
            """
            
            try:
                result = self.ch_client.query(metrics_query)
                if result:
                    m = result[0]
                    
                    # Get task metrics from PostgreSQL
                    overdue = self.pg_client.execute_query("""
                        SELECT COUNT(*) as cnt FROM tasks 
                        WHERE assignee_employee_id = %s 
                        AND status_category != 'done'
                        AND due_date < CURRENT_DATE
                    """, (employee_id,))
                    
                    blocked = self.pg_client.execute_query("""
                        SELECT COUNT(*) as cnt FROM tasks 
                        WHERE assignee_employee_id = %s 
                        AND status_category = 'blocked'
                    """, (employee_id,))
                    
                    # Upsert monthly metrics
                    self.pg_client.execute_write("""
                        INSERT INTO employee_monthly_metrics (
                            employee_id, month, tasks_completed, tasks_started,
                            overdue_open, blocked_items, prs_merged_count, pr_reviews_count,
                            generated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (employee_id, month) DO UPDATE SET
                            tasks_completed = EXCLUDED.tasks_completed,
                            tasks_started = EXCLUDED.tasks_started,
                            overdue_open = EXCLUDED.overdue_open,
                            blocked_items = EXCLUDED.blocked_items,
                            prs_merged_count = EXCLUDED.prs_merged_count,
                            pr_reviews_count = EXCLUDED.pr_reviews_count,
                            generated_at = NOW()
                    """, (
                        employee_id,
                        month_start,
                        m.get('tasks_completed', 0),
                        m.get('tasks_started', 0),
                        overdue[0]['cnt'] if overdue else 0,
                        blocked[0]['cnt'] if blocked else 0,
                        m.get('prs_merged', 0),
                        m.get('pr_reviews', 0)
                    ))
                    metrics_updated += 1
                    
            except Exception as e:
                logger.error(f"Error computing metrics for {emp['email']}: {e}")
        
        return {
            "success": True,
            "month": month,
            "employees_processed": metrics_updated,
            "message": f"Computed metrics for {metrics_updated} employees for {month}"
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _resolve_employee_id(self, source: str, external_id: str) -> Optional[str]:
        """Resolve external ID to employee UUID via identity_mappings."""
        if not external_id:
            return None
        
        result = self.pg_client.execute_query("""
            SELECT employee_id FROM identity_mappings 
            WHERE source = %s AND (external_id = %s OR external_username = %s)
            LIMIT 1
        """, (source, external_id, external_id))
        
        if result:
            return str(result[0]['employee_id'])
        
        # Fallback: Try to match by email in employees table
        result = self.pg_client.execute_query(
            "SELECT id FROM employees WHERE email ILIKE %s LIMIT 1",
            (f"%{external_id}%",)
        )
        return str(result[0]['id']) if result else None
    
    def _resolve_project_id(self, project_key: str) -> Optional[str]:
        """Resolve project key to project UUID."""
        if not project_key:
            return None
        
        result = self.pg_client.execute_query("""
            SELECT id FROM projects 
            WHERE jira_project_key = %s OR github_repo ILIKE %s OR name ILIKE %s
            LIMIT 1
        """, (project_key, f"%{project_key}%", f"%{project_key}%"))
        
        return str(result[0]['id']) if result else None
    
    # =========================================================================
    # FULL SYNC
    # =========================================================================
    
    def run_full_sync(self, since_hours: int = 24) -> Dict[str, Any]:
        """
        Run all sync operations.
        """
        logger.info(f"Running full sync (last {since_hours}h)")
        
        results = {
            "tasks": self.sync_tasks_from_jira(since_hours),
            "task_events": self.sync_task_events(since_hours),
            "task_participants": self.sync_task_participants(since_hours),
            "ci_pipelines": self.sync_ci_pipelines(since_hours),
        }
        
        return {
            "success": True,
            "results": results,
            "message": "Full sync completed"
        }


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analytics Processor")
    parser.add_argument("--sync", choices=["tasks", "events", "participants", "ci", "metrics", "all"],
                        help="What to sync")
    parser.add_argument("--hours", type=int, default=24, help="Look back hours")
    parser.add_argument("--month", type=str, help="Month for metrics (YYYY-MM)")
    
    args = parser.parse_args()
    
    processor = AnalyticsProcessor()
    
    try:
        if args.sync == "tasks":
            result = processor.sync_tasks_from_jira(args.hours)
        elif args.sync == "events":
            result = processor.sync_task_events(args.hours)
        elif args.sync == "participants":
            result = processor.sync_task_participants(args.hours)
        elif args.sync == "ci":
            result = processor.sync_ci_pipelines(args.hours)
        elif args.sync == "metrics":
            result = processor.compute_monthly_metrics(args.month)
        elif args.sync == "all":
            result = processor.run_full_sync(args.hours)
        else:
            print("Usage: python analytics_processor.py --sync [tasks|events|participants|ci|metrics|all]")
            sys.exit(1)
        
        print(json.dumps(result, indent=2, default=str))
        
    finally:
        processor.close()
