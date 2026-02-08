"""
ClickHouse tools with Pydantic validation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_core.tools import StructuredTool
from pydantic import ValidationError
from datetime import datetime, timezone

from clickhouse.clickhouse_client import ClickHouseClient
from agent.schemas.tool_schemas import (
    InsertCommitEventInput,
    InsertCommitEventArgs,
    InsertPREventInput,
    InsertPREventArgs,
    InsertJiraEventInput,
    InsertJiraEventArgs,
    InsertEventOutput,
    DeveloperActivityInput,
    DeveloperActivityOutput,
    DORAMetricsInput,
    DORAMetricsOutput
)


def insert_commit_event(
    project_id: str,
    developer_email: str,
    sha: str,
    message: str,
    files_changed: int,
    lines_added: int,
    lines_deleted: int
) -> dict:
    """
    Insert GitHub commit event into ClickHouse time-series database.
    
    Args:
        project_id: Project identifier
        developer_email: Developer's email address
        sha: Git commit SHA
        message: Commit message
        files_changed: Number of files changed
        lines_added: Lines added
        lines_deleted: Lines deleted
    
    Returns:
        dict: Success status and details
    """
    try:
        from agent.schemas.tool_schemas import CommitData
        
        # Validate input
        commit_data = CommitData(
            sha=sha,
            message=message,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            timestamp=datetime.now(timezone.utc)
        )
        
        input_data = InsertCommitEventInput(
            project_id=project_id,
            developer_email=developer_email,
            commit_data=commit_data
        )
        
        # Insert into ClickHouse
        client = ClickHouseClient()
        client.insert_event({
            "source": "github",
            "event_type": "commit_pushed",
            "project_id": input_data.project_id,
            "actor_id": input_data.developer_email,
            "entity_id": commit_data.sha,
            "entity_type": "commit",
            "metadata": {
                "sha": commit_data.sha,
                "message": commit_data.message,
                "files_changed": commit_data.files_changed,
                "lines_added": commit_data.lines_added,
                "lines_deleted": commit_data.lines_deleted
            }
        })
        client.close()
        
        # Return validated output
        output = InsertEventOutput(
            success=True,
            message=f"Inserted commit event {sha[:7]} for {developer_email}",
            event_type="commit_pushed",
            project_id=project_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "event_type": "commit_pushed",
            "project_id": project_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "event_type": "commit_pushed",
            "project_id": project_id
        }


def insert_pr_event(
    project_id: str,
    developer_email: str,
    pr_number: int,
    action: str,
    review_time_hours: float = None,
    lines_changed: int = None
) -> dict:
    """
    Insert GitHub PR event into ClickHouse for DORA metrics.
    
    Args:
        project_id: Project identifier
        developer_email: Developer's email address
        pr_number: Pull request number
        action: PR action (opened, merged, reviewed, closed)
        review_time_hours: Time from creation to merge (for DORA lead time)
        lines_changed: Total lines changed in PR
    
    Returns:
        dict: Success status and details
    """
    try:
        from agent.schemas.tool_schemas import PRData
        
        # Validate input
        pr_data = PRData(
            pr_number=pr_number,
            action=action,
            review_time_hours=review_time_hours,
            lines_changed=lines_changed
        )
        
        input_data = InsertPREventInput(
            project_id=project_id,
            developer_email=developer_email,
            pr_data=pr_data
        )
        
        # Insert into ClickHouse
        client = ClickHouseClient()
        client.insert_event({
            "source": "github",
            "event_type": f"pr_{action}",
            "project_id": input_data.project_id,
            "actor_id": input_data.developer_email,
            "entity_id": str(pr_data.pr_number),
            "entity_type": "pull_request",
            "metadata": {
                "pr_number": pr_data.pr_number,
                "action": pr_data.action,
                "review_time_hours": pr_data.review_time_hours,
                "lines_changed": pr_data.lines_changed
            }
        })
        client.close()
        
        # Return validated output
        output = InsertEventOutput(
            success=True,
            message=f"Inserted PR #{pr_number} {action} event for {developer_email}",
            event_type=f"pr_{action}",
            project_id=project_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "event_type": "pr_event",
            "project_id": project_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "event_type": "pr_event",
            "project_id": project_id
        }


def insert_jira_event(
    project_id: str,
    developer_email: str,
    issue_key: str,
    event_type: str,
    status_from: str = None,
    status_to: str = None,
    story_points: int = None
) -> dict:
    """
    Insert Jira issue event into ClickHouse for sprint analytics.
    
    Args:
        project_id: Project identifier
        developer_email: Developer's email address
        issue_key: Jira issue key (e.g., PROJ-123)
        event_type: Event type (issue_created, issue_updated, issue_completed)
        status_from: Previous status (for transitions)
        status_to: New status (for transitions)
        story_points: Story points value
    
    Returns:
        dict: Success status and details
    """
    try:
        from agent.schemas.tool_schemas import JiraIssueData
        
        # Validate input
        issue_data = JiraIssueData(
            issue_key=issue_key,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            story_points=story_points
        )
        
        input_data = InsertJiraEventInput(
            project_id=project_id,
            developer_email=developer_email,
            issue_data=issue_data
        )
        
        # Insert into ClickHouse
        client = ClickHouseClient()
        client.insert_event({
            "source": "jira",
            "event_type": event_type,
            "project_id": input_data.project_id,
            "actor_id": input_data.developer_email,
            "entity_id": issue_data.issue_key,
            "entity_type": "jira_issue",
            "metadata": {
                "issue_key": issue_data.issue_key,
                "event_type": issue_data.event_type,
                "status_from": issue_data.status_from,
                "status_to": issue_data.status_to,
                "story_points": issue_data.story_points
            }
        })
        client.close()
        
        # Return validated output
        output = InsertEventOutput(
            success=True,
            message=f"Inserted Jira event {issue_key} ({event_type}) for {developer_email}",
            event_type=event_type,
            project_id=project_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "event_type": "jira_event",
            "project_id": project_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "event_type": "jira_event",
            "project_id": project_id
        }


def get_developer_activity_summary(
    developer_email: str,
    days: int = 30
) -> dict:
    """
    Get developer activity summary from ClickHouse time-series data.
    Use this to analyze developer productivity and contribution patterns.
    
    Args:
        developer_email: Developer's email address
        days: Number of days to look back (1-365)
    
    Returns:
        dict: Developer activity metrics (commits, PRs, reviews, issues)
    """
    try:
        # Validate input
        input_data = DeveloperActivityInput(
            developer_email=developer_email,
            days=days
        )
        
        # Query ClickHouse
        client = ClickHouseClient()
        result = client.get_developer_activity(
            actor_id=input_data.developer_email,
            days=input_data.days
        )
        client.close()
        
        # Parse results (result is a dict, not a list)
        if result and isinstance(result, dict):
            output = DeveloperActivityOutput(
                success=True,
                developer_email=developer_email,
                period_days=days,
                commits=result.get('commits', 0),
                prs_opened=result.get('prs_opened', 0),
                prs_merged=result.get('prs_merged', 0),
                reviews=result.get('reviews', 0),
                issues_completed=result.get('issues_completed', 0)
            )
        else:
            output = DeveloperActivityOutput(
                success=True,
                developer_email=developer_email,
                period_days=days,
                commits=0,
                prs_opened=0,
                prs_merged=0,
                reviews=0,
                issues_completed=0
            )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "developer_email": developer_email,
            "period_days": days,
            "commits": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "reviews": 0,
            "issues_completed": 0
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "developer_email": developer_email,
            "period_days": days,
            "commits": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "reviews": 0,
            "issues_completed": 0
        }


def get_project_dora_metrics(
   project_id: str,
    days: int = 30
) -> dict:
    """
    Get DORA metrics for a project from ClickHouse materialized view.
    DORA metrics: deployment frequency, lead time, change failure rate.
    
    Args:
        project_id: Project identifier
        days: Number of days to look back (1-365)
    
    Returns:
        dict: DORA metrics for the project
    """
    try:
        # Validate input
        input_data = DORAMetricsInput(
            project_id=project_id,
            days=days
        )
        
        # Query ClickHouse materialized view
        client = ClickHouseClient()
        result = client.get_dora_metrics(
            project_id=input_data.project_id,
            days=input_data.days
        )
        client.close()
        
        # Parse results
        if result and len(result) > 0:
            row = result[0]
            output = DORAMetricsOutput(
                success=True,
                project_id=project_id,
                period_days=days,
                deployment_frequency=row.get('deployment_frequency', 0.0),
                avg_lead_time_hours=row.get('avg_lead_time_hours', 0.0),
                prs_merged=row.get('prs_merged', 0),
                story_points_completed=row.get('story_points_completed', 0)
            )
        else:
            output = DORAMetricsOutput(
                success=True,
                project_id=project_id,
                period_days=days,
                deployment_frequency=0.0,
                avg_lead_time_hours=0.0,
                prs_merged=0,
                story_points_completed=0
            )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "project_id": project_id,
            "period_days": days,
            "deployment_frequency": 0.0,
            "avg_lead_time_hours": 0.0,
            "prs_merged": 0,
            "story_points_completed": 0
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "project_id": project_id,
            "period_days": days,
            "deployment_frequency": 0.0,
            "avg_lead_time_hours": 0.0,
            "prs_merged": 0,
            "story_points_completed": 0
        }


# ==============================================================================
# LANGCHAIN STRUCTURED TOOLS
# ==============================================================================

clickhouse_tools = [
    StructuredTool.from_function(
        func=insert_commit_event,
        name="insert_commit_event",
        description="Insert GitHub commit event into ClickHouse for time-series analytics. Use when processing git commits.",
        args_schema=InsertCommitEventArgs,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=insert_pr_event,
        name="insert_pr_event",
        description="Insert GitHub PR event into ClickHouse for DORA metrics calculation. Use when PRs are opened/merged/reviewed.",
        args_schema=InsertPREventArgs,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=insert_jira_event,
        name="insert_jira_event",
        description="Insert Jira issue event into ClickHouse for sprint analytics. Use when Jira issues are created/updated/completed.",
        args_schema=InsertJiraEventArgs,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_developer_activity_summary,
        name="get_developer_activity_summary",
        description="Get developer activity summary from ClickHouse. Use to analyze productivity or generate reports.",
        args_schema=DeveloperActivityInput,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_project_dora_metrics,
        name="get_project_dora_metrics",
        description="Get DORA metrics for a project from ClickHouse. Use to analyze deployment frequency and lead time.",
        args_schema=DORAMetricsInput,
        return_direct=False
    )
]
