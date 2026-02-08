from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncpg


@dataclass
class PostgresClient:
    dsn: str

    async def connect(self) -> asyncpg.Pool:
        return await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)


async def fetch_person_profile(pool: asyncpg.Pool, *, employee_id: Optional[str], email: Optional[str]) -> Dict[str, Any]:
    if not employee_id and not email:
        raise ValueError("Must provide employee_id or email")

    # Schema note (from live DB introspection): there is no `users` table.
    # The canonical person table is `employees` with optional `teams` relationship.
    where = "e.id = $1" if employee_id else "lower(e.email) = lower($1)"
    value = employee_id or email

    row = await pool.fetchrow(
        f"""
        SELECT
            e.id::text as id,
            e.email,
            e.name,
            e.role,
            e.department,
            e.hire_date,
            t.id::text as team_id,
            t.name as team_name
        FROM employees e
        LEFT JOIN teams t ON t.id = e.team_id
        WHERE {where}
        LIMIT 1
        """,
        value,
    )

    if not row:
        return {}

    return dict(row)


async def fetch_person_projects(pool: asyncpg.Pool, *, user_id: str) -> List[Dict[str, Any]]:
    # Best-effort: this schema exists, but may be empty in hackathon DBs.
    # We keep it optional so the agent still works even when there are no assignments.
    try:
        rows = await pool.fetch(
            """
            SELECT
                p.id::text as id,
                p.name,
                p.description,
                p.github_repo,
                p.jira_project_key,
                p.status,
                p.priority,
                p.target_date,
                pa.role as assignment_role,
                pa.allocated_percent
            FROM project_assignments pa
            JOIN projects p ON p.id = pa.project_id
            WHERE pa.employee_id = $1::uuid
            ORDER BY p.priority DESC NULLS LAST, p.name ASC
            """,
            user_id,
        )
        return [dict(r) for r in rows]
    except Exception:
        return []


async def list_tables(pool: asyncpg.Pool) -> List[str]:
    rows = await pool.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
    )
    return [str(r["table_name"]) for r in rows]
