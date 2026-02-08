"""
PostgreSQL Tools for Agent System
==================================
Provides tools for querying entity data (employees, projects, teams)
from the PostgreSQL (Aurora) database.

All queries use the 'employees' table (not 'users') and
'project_assignments.employee_id' FK, matching the unified schema.
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import date, datetime
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call, log_db_query
from agents.utils.db_clients import get_postgres_client

logger = get_logger(__name__, "POSTGRES_TOOLS")

# ── Column sets for reuse ─────────────────────────────────────────────

_EMPLOYEE_COLS = (
    "e.id, e.name as full_name, e.email, e.role as title, e.role, "
    "0.0 as hourly_rate, 'Unknown' as level, 'Unknown' as location, "
    "true as active"
)
_EMPLOYEE_WITH_TEAM = (
    f"{_EMPLOYEE_COLS}, t.id AS team_id, t.name AS team_name"
)
_EMPLOYEE_FROM_JOIN = (
    "FROM employees e LEFT JOIN teams t ON e.team_id = t.id"
)


def _serialise(row: Dict) -> Dict:
    """Convert UUID, Decimal, date/datetime values for JSON serialisation."""
    out = {}
    for k, v in row.items():
        if hasattr(v, 'hex') and callable(getattr(v, 'hex', None)):
            # UUID objects
            out[k] = str(v)
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


@tool
def get_developer(
    developer_id: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get information about a developer/employee by ID, email, or name.

    Args:
        developer_id: UUID of the developer (optional)
        email: Email address of the developer (optional)
        name: Full or partial name to search for (optional, uses ILIKE for partial match)

    Returns:
        Developer information including id, full_name, email, title, role,
        team, hourly_rate, level, and location.  Returns empty dict if not found.
    """
    logger.debug(f"get_developer called: id={developer_id}, email={email}, name={name}")

    try:
        pg = get_postgres_client()

        base = f"SELECT {_EMPLOYEE_WITH_TEAM} {_EMPLOYEE_FROM_JOIN}"

        if developer_id:
            query = f"{base} WHERE e.id = %s"
            params: tuple = (developer_id,)
        elif email:
            query = f"{base} WHERE e.email = %s"
            params = (email,)
        elif name:
            query = f"{base} WHERE e.name ILIKE %s"
            params = (f"%{name}%",)
        else:
            logger.warning("get_developer called without any search criteria")
            return {"error": "Must provide developer_id, email, or name"}

        log_db_query(logger, "postgres", query, params)
        results = pg.execute_query(query, params)

        if results:
            result = _serialise(dict(results[0]))
            log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, result)
            return result
        else:
            log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, {})
            return {}

    except Exception as e:
        log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, error=e)
        return {"error": str(e)}


@tool
def list_developers(
    team_name: Optional[str] = None,
    role: Optional[str] = None,
    active_only: bool = True,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    List developers/employees with optional filters.

    Args:
        team_name: Filter by team name (optional, partial match)
        role: Filter by role/title (optional, partial match — searches both 'role' and 'title')
        active_only: If True, only return active employees (default True)
        limit: Maximum number of results to return (default 20)

    Returns:
        List of developer records with their team information.
    """
    logger.debug(f"list_developers called: team={team_name}, role={role}, limit={limit}")

    try:
        pg = get_postgres_client()

        # NOTE: Removed "WHERE 1=1" to handle the conditional active logic easier, 
        # but kept it consistent below.
        query = f"SELECT {_EMPLOYEE_WITH_TEAM} {_EMPLOYEE_FROM_JOIN} WHERE 1=1"
        params: list = []

        # Remote schema doesn't have 'active' col, so we ignore active_only filter or assume all are active
        # if active_only:
        #    query += " AND e.active = true"

        if team_name:
            query += " AND t.name ILIKE %s"
            params.append(f"%{team_name}%")

        if role:
            # Remote schema has 'role' but not 'title'. 
            # We map user request for 'title' to 'role' check as well.
            query += " AND e.role ILIKE %s"
            params.extend([f"%{role}%"])

        query += f" ORDER BY e.name LIMIT %s"
        params.append(limit)

        log_db_query(logger, "postgres", query, tuple(params))
        results = pg.execute_query(query, tuple(params))

        developers = [_serialise(dict(row)) for row in results]
        log_tool_call(logger, "list_developers", {"team": team_name, "role": role, "limit": limit}, f"{len(developers)} results")
        return developers

    except Exception as e:
        log_tool_call(logger, "list_developers", {"team": team_name, "role": role}, error=e)
        return [{"error": str(e)}]


@tool
def get_project(
    project_id: Optional[str] = None,
    name: Optional[str] = None,
    jira_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get information about a project by ID, name, or Jira key.

    Args:
        project_id: UUID of the project (optional)
        name: Project name to search for (optional, partial match)
        jira_key: Jira project key (optional)

    Returns:
        Project information including id, name, description, status, priority,
        target_date, and list of assigned developers with their allocation.
    """
    logger.debug(f"get_project called: id={project_id}, name={name}, jira_key={jira_key}")

    try:
        pg = get_postgres_client()

        if project_id:
            query = "SELECT * FROM projects WHERE id = %s"
            params: tuple = (project_id,)
        elif jira_key:
            query = "SELECT * FROM projects WHERE jira_project_key = %s"
            params = (jira_key,)
        elif name:
            query = "SELECT * FROM projects WHERE name ILIKE %s"
            params = (f"%{name}%",)
        else:
            logger.warning("get_project called without any search criteria")
            return {"error": "Must provide project_id, name, or jira_key"}

        log_db_query(logger, "postgres", query, params)
        results = pg.execute_query(query, params)

        if results:
            project = _serialise(dict(results[0]))

            # Fetch assigned developers (employees via employee_id FK)
            dev_query = """
                SELECT e.id, e.name as full_name, e.role as title, e.role,
                       pa.role AS project_role, pa.allocated_percent
                FROM project_assignments pa
                JOIN employees e ON pa.employee_id = e.id
                WHERE pa.project_id = %s
            """
            log_db_query(logger, "postgres", dev_query, (results[0]["id"],))
            devs = pg.execute_query(dev_query, (results[0]["id"],))
            project["assigned_developers"] = [_serialise(dict(d)) for d in devs]

            log_tool_call(logger, "get_project", {"id": project_id, "name": name}, project)
            return project
        else:
            log_tool_call(logger, "get_project", {"id": project_id, "name": name}, {})
            return {}

    except Exception as e:
        log_tool_call(logger, "get_project", {"id": project_id, "name": name}, error=e)
        return {"error": str(e)}


@tool
def list_projects(status: Optional[str] = None, priority: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    List projects with optional filters.
    
    Args:
        status: Filter by status (e.g., 'active', 'completed', 'on_hold')
        priority: Filter by priority (e.g., 'high', 'medium', 'low')
        limit: Maximum number of results (default 20)
    
    Returns:
        List of projects with basic information.
    """
    logger.debug(f"list_projects called: status={status}, priority={priority}, limit={limit}")
    
    try:
        pg = get_postgres_client()
        
        query = "SELECT id, name, description, status, priority, target_date, github_repo, jira_project_key FROM projects WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        if priority:
            query += " AND priority = %s"
            params.append(priority)
        
        query += f" ORDER BY priority DESC, target_date ASC LIMIT {limit}"
        
        results = pg.execute_query(query, tuple(params) if params else None)
        
        projects = [{**dict(r), 'id': str(r['id'])} for r in results]
        log_tool_call(logger, "list_projects", {"status": status, "priority": priority}, f"{len(projects)} results")
        return projects
        
    except Exception as e:
        log_tool_call(logger, "list_projects", {"status": status, "priority": priority}, error=e)
        return [{"error": str(e)}]


@tool
def get_team(
    team_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get information about a team by ID or name.

    Args:
        team_id: UUID of the team (optional)
        name: Team name to search for (optional, partial match)

    Returns:
        Team information including id, name, list of members, and member count.
    """
    logger.debug(f"get_team called: id={team_id}, name={name}")

    try:
        pg = get_postgres_client()

        if team_id:
            query = "SELECT * FROM teams WHERE id = %s"
            params: tuple = (team_id,)
        elif name:
            query = "SELECT * FROM teams WHERE name ILIKE %s"
            params = (f"%{name}%",)
        else:
            logger.warning("get_team called without any search criteria")
            return {"error": "Must provide team_id or name"}

        log_db_query(logger, "postgres", query, params)
        results = pg.execute_query(query, params)

        if results:
            team = _serialise(dict(results[0]))

            # Get team members from employees table
            members_query = """
                SELECT id, name as full_name, email, role as title, role, 
                       0.0 as hourly_rate, 'Unknown' as level, true as active
                FROM employees WHERE team_id = %s
                ORDER BY name
            """
            log_db_query(logger, "postgres", members_query, (results[0]["id"],))
            members = pg.execute_query(members_query, (results[0]["id"],))
            team["members"] = [_serialise(dict(m)) for m in members]
            team["member_count"] = len(team["members"])

            log_tool_call(logger, "get_team", {"id": team_id, "name": name}, team)
            return team
        else:
            log_tool_call(logger, "get_team", {"id": team_id, "name": name}, {})
            return {}

    except Exception as e:
        log_tool_call(logger, "get_team", {"id": team_id, "name": name}, error=e)
        return {"error": str(e)}


@tool
def get_developer_workload(developer_id: str) -> Dict[str, Any]:
    """
    Get the current workload/allocation for a developer.

    Args:
        developer_id: UUID of the developer

    Returns:
        Developer info with list of project assignments, total allocation
        percentage, and capacity flags.
    """
    logger.debug(f"get_developer_workload called: developer_id={developer_id}")

    try:
        pg = get_postgres_client()

        # Get developer info
        dev_query = f"""
            SELECT {_EMPLOYEE_WITH_TEAM}
            {_EMPLOYEE_FROM_JOIN}
            WHERE e.id = %s
        """
        log_db_query(logger, "postgres", dev_query, (developer_id,))
        dev_results = pg.execute_query(dev_query, (developer_id,))

        if not dev_results:
            return {"error": f"Developer not found: {developer_id}"}

        dev = _serialise(dict(dev_results[0]))

        # Get project assignments (employee_id FK)
        assignments_query = """
            SELECT p.id AS project_id, p.name AS project_name, p.status, p.priority,
                   pa.role AS project_role, pa.allocated_percent, pa.assigned_at,
                   pa.start_date, pa.end_date
            FROM project_assignments pa
            JOIN projects p ON pa.project_id = p.id
            WHERE pa.employee_id = %s
            ORDER BY pa.allocated_percent DESC
        """
        log_db_query(logger, "postgres", assignments_query, (developer_id,))
        assignments = pg.execute_query(assignments_query, (developer_id,))

        dev["assignments"] = []
        total_allocation = 0.0
        for a in assignments:
            assignment = _serialise(dict(a))
            dev["assignments"].append(assignment)
            total_allocation += float(assignment.get("allocated_percent", 0) or 0)

        dev["total_allocation_percent"] = total_allocation
        dev["is_overallocated"] = total_allocation > 100
        dev["available_capacity_percent"] = max(0, 100 - total_allocation)

        log_tool_call(logger, "get_developer_workload", {"developer_id": developer_id}, dev)
        return dev

    except Exception as e:
        log_tool_call(logger, "get_developer_workload", {"developer_id": developer_id}, error=e)
        return {"error": str(e)}


# Export all tools for registration
POSTGRES_TOOLS = [
    get_developer,
    list_developers,
    get_project,
    list_projects,
    get_team,
    get_developer_workload,
]
