"""
Schema Compatibility Layer
==========================
Auto-detects whether the database uses the legacy 'users' schema or the new
'employees' schema and provides column-name mappings so tool code can be
written once against a canonical interface.

The canonical (target) column names match the *new* unified_schema.sql:
    employees.id, employees.full_name, employees.email, employees.title,
    employees.team_id, project_assignments.employee_id, etc.

If the database still has the legacy 'users' table the layer transparently
maps: users.name -> full_name, users.role -> title, users.hourly_rate -> hourly_rate,
      project_assignments.user_id -> employee_id.
"""

from typing import Dict, Optional
from agents.utils.logger import get_logger

logger = get_logger(__name__, "SCHEMA")

# Cached detection result
_schema_info: Optional[Dict] = None


def detect_schema(pg_client) -> Dict:
    """
    Probe the database once and return a dict describing the active schema.

    Returns:
        {
            "person_table": "employees" | "users",
            "person_name_col": "full_name" | "name",
            "person_role_col": "title" | "role",
            "person_has_hourly_rate": bool,
            "assignment_person_fk": "employee_id" | "user_id",
        }
    """
    global _schema_info
    if _schema_info is not None:
        return _schema_info

    info: Dict = {}

    # Check which table exists
    try:
        rows = pg_client.execute_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('employees', 'users')"
        )
        tables = {r["table_name"] for r in rows}
    except Exception as e:
        logger.error(f"Schema detection failed: {e}")
        # Fallback to legacy assumption
        tables = {"users"}

    if "employees" in tables:
        info["person_table"] = "employees"
        info["person_name_col"] = "full_name"
        info["person_role_col"] = "title"
    else:
        info["person_table"] = "users"
        info["person_name_col"] = "name"
        info["person_role_col"] = "role"

    # Check for hourly_rate column
    try:
        cols = pg_client.execute_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'hourly_rate'",
            (info["person_table"],),
        )
        info["person_has_hourly_rate"] = len(cols) > 0
    except Exception:
        info["person_has_hourly_rate"] = False

    # Check assignment FK column
    try:
        cols = pg_client.execute_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'project_assignments' "
            "AND column_name IN ('employee_id', 'user_id')"
        )
        fk_cols = {r["column_name"] for r in cols}
        info["assignment_person_fk"] = "employee_id" if "employee_id" in fk_cols else "user_id"
    except Exception:
        info["assignment_person_fk"] = "user_id"

    _schema_info = info
    logger.info(
        f"Schema detected: table={info['person_table']}, "
        f"name_col={info['person_name_col']}, role_col={info['person_role_col']}, "
        f"hourly_rate={info['person_has_hourly_rate']}, fk={info['assignment_person_fk']}"
    )
    return info


def get_schema_info(pg_client) -> Dict:
    """Return cached schema info (calls detect_schema on first invocation)."""
    return detect_schema(pg_client)


def person_select_cols(schema: Dict, table_alias: str = "p") -> str:
    """
    Return the SELECT column list for the person table,
    aliased to canonical names so downstream code always sees
    id, full_name, email, title, team_id.
    """
    t = table_alias
    name_col = schema["person_name_col"]
    role_col = schema["person_role_col"]
    parts = [
        f"{t}.id",
        f"{t}.{name_col} AS full_name",
        f"{t}.email",
        f"{t}.{role_col} AS title",
    ]
    if schema["person_has_hourly_rate"]:
        parts.append(f"{t}.hourly_rate")
    parts.append(f"{t}.team_id")
    return ", ".join(parts)


def person_table(schema: Dict) -> str:
    """Return the person table name."""
    return schema["person_table"]


def assignment_fk(schema: Dict) -> str:
    """Return the FK column name in project_assignments that points to the person."""
    return schema["assignment_person_fk"]


def reset_cache():
    """Reset cached schema info (useful for testing)."""
    global _schema_info
    _schema_info = None
