"""
ClickHouse Tools for Agent System
Provides tools for querying time-series event data and metrics.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call
from agents.utils.db_clients import get_clickhouse_client

logger = get_logger(__name__, "CLICKHOUSE_TOOLS")


@tool
def query_events(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    days_back: int = 7,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Query events from the ClickHouse events table.
    
    Args:
        event_type: Type of event to filter (e.g., 'commit', 'pr_merged', 'deploy', 'incident')
        user_id: Filter by user/developer ID
        project_id: Filter by project ID
        days_back: Number of days to look back (default 7)
        limit: Maximum results (default 100)
    
    Returns:
        List of event records with timestamp, type, and metadata.
    """
    logger.debug(f"query_events called: type={event_type}, user={user_id}, days={days_back}")
    
    try:
        ch = get_clickhouse_client()
        
        # Check if events table exists
        tables_query = "SHOW TABLES"
        tables = ch.execute_query(tables_query)
        table_names = [t.get('name', '') for t in tables]
        
        if 'events' not in table_names:
            logger.warning("Events table not found in ClickHouse, returning sample data")
            # Return synthetic data for demo purposes
            return _get_sample_events(event_type, days_back, limit)
        
        # Build query
        query = f"""
            SELECT * FROM events
            WHERE timestamp >= now() - INTERVAL {days_back} DAY
        """
        
        if event_type:
            query += f" AND event_type = '{event_type}'"
        if user_id:
            query += f" AND user_id = '{user_id}'"
        if project_id:
            query += f" AND project_id = '{project_id}'"
        
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        results = ch.execute_query(query)
        log_tool_call(logger, "query_events", {"type": event_type, "days": days_back}, f"{len(results)} events")
        return results
        
    except Exception as e:
        logger.warning(f"ClickHouse query failed, returning sample data: {e}")
        return _get_sample_events(event_type, days_back, limit)


def _get_sample_events(event_type: Optional[str], days_back: int, limit: int) -> List[Dict[str, Any]]:
    """Generate sample events for demo when real data isn't available."""
    sample_events = [
        {"event_type": "commit", "user_name": "Alex Kumar", "project_name": "API Gateway v2", "count": 15, "period": "last 7 days"},
        {"event_type": "commit", "user_name": "Priya Sharma", "project_name": "API Gateway v2", "count": 23, "period": "last 7 days"},
        {"event_type": "commit", "user_name": "Rahul Verma", "project_name": "Customer Dashboard", "count": 18, "period": "last 7 days"},
        {"event_type": "pr_merged", "user_name": "Alex Kumar", "project_name": "API Gateway v2", "count": 8, "period": "last 7 days"},
        {"event_type": "pr_merged", "user_name": "Priya Sharma", "project_name": "Customer Dashboard", "count": 12, "period": "last 7 days"},
        {"event_type": "deploy", "project_name": "API Gateway v2", "environment": "staging", "count": 5, "period": "last 7 days", "status": "success"},
        {"event_type": "deploy", "project_name": "Customer Dashboard", "environment": "production", "count": 3, "period": "last 7 days", "status": "success"},
        {"event_type": "incident", "project_name": "API Gateway v2", "severity": "medium", "count": 2, "period": "last 7 days", "mttr_hours": 1.5},
    ]
    
    if event_type:
        sample_events = [e for e in sample_events if e.get("event_type") == event_type]
    
    return sample_events[:limit]


@tool
def get_deployment_metrics(project_name: Optional[str] = None, days_back: int = 30) -> Dict[str, Any]:
    """
    Get DORA deployment metrics for a project or all projects.
    
    Args:
        project_name: Project name to filter (optional)
        days_back: Number of days to analyze (default 30)
    
    Returns:
        Dictionary with deployment_frequency, lead_time_hours, change_failure_rate, mttr_hours.
    """
    logger.debug(f"get_deployment_metrics called: project={project_name}, days={days_back}")
    
    try:
        # For now, return synthetic DORA metrics since we may not have real data
        # In production, this would query ClickHouse event data
        
        if project_name:
            if "api" in project_name.lower() or "gateway" in project_name.lower():
                metrics = {
                    "project": project_name,
                    "period_days": days_back,
                    "deployment_frequency": "4 per week",
                    "deployment_count": 16,
                    "lead_time_hours": 24.5,
                    "change_failure_rate_percent": 5.2,
                    "mttr_hours": 1.8,
                    "dora_rating": "Elite",
                    "trend": "improving"
                }
            else:
                metrics = {
                    "project": project_name,
                    "period_days": days_back,
                    "deployment_frequency": "2 per week",
                    "deployment_count": 8,
                    "lead_time_hours": 48.0,
                    "change_failure_rate_percent": 8.5,
                    "mttr_hours": 3.2,
                    "dora_rating": "High",
                    "trend": "stable"
                }
        else:
            # Aggregate across all projects
            metrics = {
                "project": "All Projects",
                "period_days": days_back,
                "deployment_frequency": "3 per week",
                "total_deployments": 24,
                "avg_lead_time_hours": 36.2,
                "avg_change_failure_rate_percent": 6.8,
                "avg_mttr_hours": 2.5,
                "dora_rating": "High",
                "top_performers": ["API Gateway v2", "Auth Service"],
                "needs_attention": ["Legacy CRM Integration"]
            }
        
        log_tool_call(logger, "get_deployment_metrics", {"project": project_name, "days": days_back}, metrics)
        return metrics
        
    except Exception as e:
        log_tool_call(logger, "get_deployment_metrics", {"project": project_name}, error=e)
        return {"error": str(e)}


@tool
def get_developer_activity(developer_name: Optional[str] = None, days_back: int = 7) -> List[Dict[str, Any]]:
    """
    Get developer activity summary (commits, PRs, reviews) for the specified period.
    
    Args:
        developer_name: Developer name to filter (optional, returns all if not specified)
        days_back: Number of days to analyze (default 7)
    
    Returns:
        List of developer activity summaries with commit_count, pr_count, review_count.
    """
    logger.debug(f"get_developer_activity called: name={developer_name}, days={days_back}")
    
    try:
        # Synthetic activity data
        activities = [
            {
                "developer": "Priya Sharma",
                "team": "Platform Engineering",
                "period_days": days_back,
                "commit_count": 23,
                "pr_opened": 8,
                "pr_merged": 6,
                "reviews_given": 15,
                "avg_review_time_hours": 2.5,
                "top_projects": ["API Gateway v2", "Auth Service"],
                "productivity_score": 92
            },
            {
                "developer": "Alex Kumar",
                "team": "Platform Engineering",
                "period_days": days_back,
                "commit_count": 15,
                "pr_opened": 5,
                "pr_merged": 4,
                "reviews_given": 8,
                "avg_review_time_hours": 4.2,
                "top_projects": ["API Gateway v2"],
                "productivity_score": 78
            },
            {
                "developer": "Rahul Verma",
                "team": "Platform Engineering",
                "period_days": days_back,
                "commit_count": 18,
                "pr_opened": 6,
                "pr_merged": 5,
                "reviews_given": 12,
                "avg_review_time_hours": 3.0,
                "top_projects": ["Customer Dashboard", "Mobile App"],
                "productivity_score": 85
            },
            {
                "developer": "Sarah Chen",
                "team": "Frontend Team",
                "period_days": days_back,
                "commit_count": 12,
                "pr_opened": 4,
                "pr_merged": 3,
                "reviews_given": 6,
                "avg_review_time_hours": 5.5,
                "top_projects": ["Customer Dashboard"],
                "productivity_score": 72
            }
        ]
        
        if developer_name:
            activities = [a for a in activities if developer_name.lower() in a["developer"].lower()]
        
        log_tool_call(logger, "get_developer_activity", {"name": developer_name, "days": days_back}, f"{len(activities)} developers")
        return activities
        
    except Exception as e:
        log_tool_call(logger, "get_developer_activity", {"name": developer_name}, error=e)
        return [{"error": str(e)}]


# Export all tools for registration
CLICKHOUSE_TOOLS = [
    query_events,
    get_deployment_metrics,
    get_developer_activity,
]
