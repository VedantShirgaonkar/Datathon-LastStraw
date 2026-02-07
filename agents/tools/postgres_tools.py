"""
PostgreSQL Tools for Agent System
Provides tools for querying entity data (users, projects, teams).
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

from agents.utils.logger import get_logger, log_tool_call
from agents.utils.db_clients import get_postgres_client

logger = get_logger(__name__, "POSTGRES_TOOLS")


@tool
def get_developer(developer_id: Optional[str] = None, email: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get information about a developer/user by ID, email, or name.
    
    Args:
        developer_id: UUID of the developer (optional)
        email: Email address of the developer (optional)
        name: Full or partial name to search for (optional, uses ILIKE for partial match)
    
    Returns:
        Developer information including id, name, email, role, team, and hourly_rate.
        Returns empty dict if not found.
    """
    logger.debug(f"get_developer called: id={developer_id}, email={email}, name={name}")
    
    try:
        pg = get_postgres_client()
        
        if developer_id:
            query = """
                SELECT u.id, u.name, u.email, u.role, u.hourly_rate,
                       t.id as team_id, t.name as team_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                WHERE u.id = %s
            """
            results = pg.execute_query(query, (developer_id,))
        elif email:
            query = """
                SELECT u.id, u.name, u.email, u.role, u.hourly_rate,
                       t.id as team_id, t.name as team_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                WHERE u.email = %s
            """
            results = pg.execute_query(query, (email,))
        elif name:
            query = """
                SELECT u.id, u.name, u.email, u.role, u.hourly_rate,
                       t.id as team_id, t.name as team_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                WHERE u.name ILIKE %s
            """
            results = pg.execute_query(query, (f"%{name}%",))
        else:
            logger.warning("get_developer called without any search criteria")
            return {"error": "Must provide developer_id, email, or name"}
        
        if results:
            result = dict(results[0])
            # Convert UUID to string for JSON serialization
            result['id'] = str(result['id'])
            if result.get('team_id'):
                result['team_id'] = str(result['team_id'])
            log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, result)
            return result
        else:
            log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, {})
            return {}
            
    except Exception as e:
        log_tool_call(logger, "get_developer", {"id": developer_id, "email": email, "name": name}, error=e)
        return {"error": str(e)}


@tool
def list_developers(team_name: Optional[str] = None, role: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    List developers/users with optional filters.
    
    Args:
        team_name: Filter by team name (optional, partial match)
        role: Filter by role/title (optional, partial match)
        limit: Maximum number of results to return (default 20)
    
    Returns:
        List of developer records with their team information.
    """
    logger.debug(f"list_developers called: team={team_name}, role={role}, limit={limit}")
    
    try:
        pg = get_postgres_client()
        
        query = """
            SELECT u.id, u.name, u.email, u.role, u.hourly_rate,
                   t.id as team_id, t.name as team_name
            FROM users u
            LEFT JOIN teams t ON u.team_id = t.id
            WHERE 1=1
        """
        params = []
        
        if team_name:
            query += " AND t.name ILIKE %s"
            params.append(f"%{team_name}%")
        
        if role:
            query += " AND u.role ILIKE %s"
            params.append(f"%{role}%")
        
        query += f" ORDER BY u.name LIMIT {limit}"
        
        results = pg.execute_query(query, tuple(params) if params else None)
        
        # Convert UUIDs to strings
        developers = []
        for row in results:
            dev = dict(row)
            dev['id'] = str(dev['id'])
            if dev.get('team_id'):
                dev['team_id'] = str(dev['team_id'])
            developers.append(dev)
        
        log_tool_call(logger, "list_developers", {"team": team_name, "role": role, "limit": limit}, f"{len(developers)} results")
        return developers
        
    except Exception as e:
        log_tool_call(logger, "list_developers", {"team": team_name, "role": role}, error=e)
        return [{"error": str(e)}]


@tool
def get_project(project_id: Optional[str] = None, name: Optional[str] = None, jira_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Get information about a project by ID, name, or Jira key.
    
    Args:
        project_id: UUID of the project (optional)
        name: Project name to search for (optional, partial match)
        jira_key: Jira project key (optional)
    
    Returns:
        Project information including id, name, description, status, priority, and team assignments.
    """
    logger.debug(f"get_project called: id={project_id}, name={name}, jira_key={jira_key}")
    
    try:
        pg = get_postgres_client()
        
        if project_id:
            query = "SELECT * FROM projects WHERE id = %s"
            results = pg.execute_query(query, (project_id,))
        elif jira_key:
            query = "SELECT * FROM projects WHERE jira_project_key = %s"
            results = pg.execute_query(query, (jira_key,))
        elif name:
            query = "SELECT * FROM projects WHERE name ILIKE %s"
            results = pg.execute_query(query, (f"%{name}%",))
        else:
            logger.warning("get_project called without any search criteria")
            return {"error": "Must provide project_id, name, or jira_key"}
        
        if results:
            project = dict(results[0])
            project['id'] = str(project['id'])
            
            # Also get assigned developers
            dev_query = """
                SELECT u.id, u.name, u.role, pa.role as project_role, pa.allocated_percent
                FROM project_assignments pa
                JOIN users u ON pa.user_id = u.id
                WHERE pa.project_id = %s
            """
            devs = pg.execute_query(dev_query, (results[0]['id'],))
            project['assigned_developers'] = [
                {**dict(d), 'id': str(d['id'])} for d in devs
            ]
            
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
def get_team(team_id: Optional[str] = None, name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get information about a team by ID or name.
    
    Args:
        team_id: UUID of the team (optional)
        name: Team name to search for (optional, partial match)
    
    Returns:
        Team information including id, name, and list of members.
    """
    logger.debug(f"get_team called: id={team_id}, name={name}")
    
    try:
        pg = get_postgres_client()
        
        if team_id:
            query = "SELECT * FROM teams WHERE id = %s"
            results = pg.execute_query(query, (team_id,))
        elif name:
            query = "SELECT * FROM teams WHERE name ILIKE %s"
            results = pg.execute_query(query, (f"%{name}%",))
        else:
            logger.warning("get_team called without any search criteria")
            return {"error": "Must provide team_id or name"}
        
        if results:
            team = dict(results[0])
            team['id'] = str(team['id'])
            
            # Get team members
            members_query = """
                SELECT id, name, email, role, hourly_rate
                FROM users WHERE team_id = %s
                ORDER BY name
            """
            members = pg.execute_query(members_query, (results[0]['id'],))
            team['members'] = [{**dict(m), 'id': str(m['id'])} for m in members]
            team['member_count'] = len(team['members'])
            
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
        Developer info with list of project assignments and total allocation percentage.
    """
    logger.debug(f"get_developer_workload called: developer_id={developer_id}")
    
    try:
        pg = get_postgres_client()
        
        # Get developer info
        dev_query = """
            SELECT u.id, u.name, u.email, u.role, t.name as team_name
            FROM users u
            LEFT JOIN teams t ON u.team_id = t.id
            WHERE u.id = %s
        """
        dev_results = pg.execute_query(dev_query, (developer_id,))
        
        if not dev_results:
            return {"error": f"Developer not found: {developer_id}"}
        
        dev = dict(dev_results[0])
        dev['id'] = str(dev['id'])
        
        # Get project assignments
        assignments_query = """
            SELECT p.id as project_id, p.name as project_name, p.status, p.priority,
                   pa.role as project_role, pa.allocated_percent, pa.assigned_at
            FROM project_assignments pa
            JOIN projects p ON pa.project_id = p.id
            WHERE pa.user_id = %s
            ORDER BY pa.allocated_percent DESC
        """
        assignments = pg.execute_query(assignments_query, (developer_id,))
        
        dev['assignments'] = []
        total_allocation = 0
        for a in assignments:
            assignment = dict(a)
            assignment['project_id'] = str(assignment['project_id'])
            dev['assignments'].append(assignment)
            total_allocation += float(assignment.get('allocated_percent', 0) or 0)
        
        dev['total_allocation_percent'] = total_allocation
        dev['is_overallocated'] = total_allocation > 100
        dev['available_capacity_percent'] = max(0, 100 - total_allocation)
        
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
