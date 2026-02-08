"""
Seed Embeddings Script
======================
Re-generates all embeddings in the pgvector `embeddings` table using
Pinecone Inference API with llama-text-embed-v2 (1024-dim).

For each employee and project, it:
  1. Builds a rich text description from the structured data.
  2. Generates a 1024-dim embedding vector via Pinecone's hosted inference.
  3. UPSERTs into the embeddings table (updates if source_id + embedding_type exists).

Requires:
  PINECONE_API_KEY environment variable set.

Usage:
    cd /Users/rahul/Desktop/Datathon
    .venv/bin/python scripts/seed_embeddings.py
"""

import sys
import uuid
import json
from datetime import datetime, timezone

sys.path.insert(0, "/Users/rahul/Desktop/Datathon")

from agents.utils.db_clients import get_postgres_client
from agents.tools.embedding_tools import get_embedding, get_embeddings, format_vector_for_pg, EMBEDDING_DIM
from agents.utils.logger import get_logger

logger = get_logger(__name__, "SEED_EMBEDDINGS")


def build_employee_text(emp: dict) -> str:
    """Build a rich text description of an employee for embedding."""
    parts = [f"{emp['full_name']}"]
    if emp.get("title"):
        parts.append(f"Title: {emp['title']}")
    if emp.get("role") and emp["role"] != emp.get("title"):
        parts.append(f"Role: {emp['role']}")
    if emp.get("team_name"):
        parts.append(f"Team: {emp['team_name']}")
    if emp.get("email"):
        parts.append(f"Email: {emp['email']}")
    if emp.get("level"):
        parts.append(f"Level: {emp['level']}")
    if emp.get("location"):
        parts.append(f"Location: {emp['location']}")
    if emp.get("employment_type"):
        parts.append(f"Employment: {emp['employment_type']}")

    # Get project assignments for this employee
    pg = get_postgres_client()
    assignments = pg.execute_query(
        "SELECT p.name, pa.role AS project_role, pa.allocated_percent "
        "FROM project_assignments pa "
        "JOIN projects p ON pa.project_id = p.id "
        "WHERE pa.employee_id = %s",
        (emp["id"],),
    )
    if assignments:
        proj_strs = []
        for a in assignments:
            proj_str = a["name"]
            if a.get("project_role"):
                proj_str += f" ({a['project_role']})"
            if a.get("allocated_percent"):
                proj_str += f" {a['allocated_percent']}%"
            proj_strs.append(proj_str)
        parts.append(f"Projects: {', '.join(proj_strs)}")

    return ". ".join(parts)


def build_project_text(proj: dict) -> str:
    """Build a rich text description of a project for embedding."""
    parts = [proj["name"]]
    if proj.get("description"):
        parts.append(f"Description: {proj['description']}")
    if proj.get("status"):
        parts.append(f"Status: {proj['status']}")
    if proj.get("priority"):
        parts.append(f"Priority: {proj['priority']}")
    if proj.get("github_repo"):
        parts.append(f"GitHub: {proj['github_repo']}")
    if proj.get("jira_project_key"):
        parts.append(f"Jira: {proj['jira_project_key']}")
    if proj.get("target_date"):
        parts.append(f"Target: {proj['target_date']}")

    # Get assigned team members
    pg = get_postgres_client()
    members = pg.execute_query(
        "SELECT e.full_name, e.title, pa.role AS project_role "
        "FROM project_assignments pa "
        "JOIN employees e ON pa.employee_id = e.id "
        "WHERE pa.project_id = %s",
        (proj["id"],),
    )
    if members:
        member_strs = [f"{m['full_name']} ({m.get('project_role', 'contributor')})" for m in members]
        parts.append(f"Team: {', '.join(member_strs)}")

    return ". ".join(parts)


def upsert_embedding(
    pg, source_id: str, source_table: str, embedding_type: str,
    title: str, content: str, embedding_vec: list, metadata: dict,
):
    """Insert or update an embedding row."""
    vec_str = format_vector_for_pg(embedding_vec)
    now = datetime.now(timezone.utc)
    metadata_json = json.dumps(metadata)

    # Check if an embedding already exists for this source
    existing = pg.execute_query(
        "SELECT id FROM embeddings WHERE source_id = %s AND embedding_type = %s",
        (source_id, embedding_type),
    )

    if existing:
        # Update existing
        pg.execute_write(
            f"UPDATE embeddings SET embedding = '{vec_str}'::vector, "
            "title = %s, content = %s, metadata = %s::jsonb, updated_at = %s "
            "WHERE source_id = %s AND embedding_type = %s",
            (title, content, metadata_json, now, source_id, embedding_type),
        )
        return "updated"
    else:
        # Insert new
        new_id = str(uuid.uuid4())
        pg.execute_write(
            f"INSERT INTO embeddings (id, embedding_type, source_id, source_table, "
            f"embedding, title, content, metadata, created_at, updated_at) "
            f"VALUES (%s, %s, %s, %s, '{vec_str}'::vector, %s, %s, %s::jsonb, %s, %s)",
            (new_id, embedding_type, source_id, source_table,
             title, content, metadata_json, now, now),
        )
        return "inserted"


def seed_employee_embeddings():
    """Generate and upsert embeddings for all active employees."""
    pg = get_postgres_client()
    employees = pg.execute_query(
        "SELECT e.*, t.name AS team_name "
        "FROM employees e LEFT JOIN teams t ON e.team_id = t.id "
        "WHERE e.active = true "
        "ORDER BY e.full_name"
    )
    logger.info(f"Generating embeddings for {len(employees)} employees...")

    texts = []
    emp_list = []
    for emp in employees:
        emp_dict = dict(emp)
        text = build_employee_text(emp_dict)
        texts.append(text)
        emp_list.append(emp_dict)
        logger.debug(f"  {emp_dict['full_name']}: {text[:80]}...")

    # Batch embed
    vectors = get_embeddings(texts)
    logger.info(f"Generated {len(vectors)} employee embeddings (dim={len(vectors[0])})")

    # Upsert
    inserted, updated = 0, 0
    for emp, text, vec in zip(emp_list, texts, vectors):
        metadata = {
            "role": emp.get("role") or emp.get("title"),
            "team": emp.get("team_name"),
            "email": emp.get("email"),
        }
        action = upsert_embedding(
            pg,
            source_id=str(emp["id"]),
            source_table="employees",
            embedding_type="developer_profile",
            title=f"{emp['full_name']} - Developer Profile",
            content=text,
            embedding_vec=vec,
            metadata=metadata,
        )
        if action == "inserted":
            inserted += 1
        else:
            updated += 1

    logger.info(f"Employee embeddings: {inserted} inserted, {updated} updated")
    return inserted, updated


def seed_project_embeddings():
    """Generate and upsert embeddings for all projects."""
    pg = get_postgres_client()
    projects = pg.execute_query("SELECT * FROM projects ORDER BY name")
    logger.info(f"Generating embeddings for {len(projects)} projects...")

    texts = []
    proj_list = []
    for proj in projects:
        proj_dict = dict(proj)
        text = build_project_text(proj_dict)
        texts.append(text)
        proj_list.append(proj_dict)
        logger.debug(f"  {proj_dict['name']}: {text[:80]}...")

    # Batch embed
    vectors = get_embeddings(texts)
    logger.info(f"Generated {len(vectors)} project embeddings (dim={len(vectors[0])})")

    # Upsert
    inserted, updated = 0, 0
    for proj, text, vec in zip(proj_list, texts, vectors):
        metadata = {
            "status": proj.get("status"),
            "priority": proj.get("priority"),
            "jira_key": proj.get("jira_project_key"),
            "github_repo": proj.get("github_repo"),
        }
        action = upsert_embedding(
            pg,
            source_id=str(proj["id"]),
            source_table="projects",
            embedding_type="project_doc",
            title=f"{proj['name']} - Project Overview",
            content=text,
            embedding_vec=vec,
            metadata=metadata,
        )
        if action == "inserted":
            inserted += 1
        else:
            updated += 1

    logger.info(f"Project embeddings: {inserted} inserted, {updated} updated")
    return inserted, updated


def main():
    print("=" * 60)
    print("Embedding Seed Script - Pinecone llama-text-embed-v2 (1024-dim)")
    print("=" * 60)

    emp_ins, emp_upd = seed_employee_embeddings()
    proj_ins, proj_upd = seed_project_embeddings()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Employees: {emp_ins} inserted, {emp_upd} updated")
    print(f"Projects:  {proj_ins} inserted, {proj_upd} updated")
    print(f"Total:     {emp_ins + proj_ins} new, {emp_upd + proj_upd} updated")

    # Verify
    pg = get_postgres_client()
    cnt = pg.execute_query("SELECT count(*) as cnt FROM embeddings")
    dims = pg.execute_query("SELECT vector_dims(embedding) as dims FROM embeddings LIMIT 1")
    print(f"\nVerification: {cnt[0]['cnt']} total embeddings, {dims[0]['dims']}-dim vectors")
    print("✅ Seeding complete!")


if __name__ == "__main__":
    main()
