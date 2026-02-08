from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from hr_voice_agent.clients.neo4j_client import Neo4jClient
from hr_voice_agent.clients.pinecone_client import PineconeClient
from hr_voice_agent.clients.postgres_client import fetch_person_profile, fetch_person_projects


@dataclass
class BuiltContext:
    person: Dict[str, Any]
    month: str
    evidence: List[Dict[str, Any]]
    warnings: List[str]


def _default_month() -> str:
    now = datetime.utcnow()
    return f"{now.year:04d}-{now.month:02d}"


async def build_context(
    *,
    month: Optional[str],
    employee_id: Optional[str],
    email: Optional[str],
    top_k: int,
    postgres_pool,
    neo4j: Optional[Neo4jClient],
    pinecone: Optional[PineconeClient],
    pinecone_namespace_developer_profiles: str,
    pinecone_namespace_project_docs: str,
    embedding_provider: str,
    openai_embed_fn,
) -> BuiltContext:
    warnings: List[str] = []
    evidence: List[Dict[str, Any]] = []

    resolved_month = (month or "").strip() or _default_month()

    person: Dict[str, Any] = {}
    projects: List[Dict[str, Any]] = []

    if postgres_pool:
        try:
            person = await fetch_person_profile(postgres_pool, employee_id=employee_id, email=email)
            if person.get("id"):
                projects = await fetch_person_projects(postgres_pool, user_id=str(person["id"]))
        except Exception as e:
            warnings.append(f"Postgres lookup failed: {e}")
    else:
        warnings.append("Postgres not configured; structured personalization is limited")

    if projects:
        evidence.append(
            {
                "source": "postgres",
                "title": "Assigned projects",
                "content": "; ".join([p.get("name") or "(unknown)" for p in projects][:15]),
                "metadata": {"projects": projects[:15]},
            }
        )

    # Neo4j relationship context
    if neo4j:
        try:
            graph = neo4j.get_person_graph_context(email=email or person.get("email"), user_id=employee_id or person.get("id"))
            if graph:
                evidence.append(
                    {
                        "source": "neo4j",
                        "title": "Team/project relationships",
                        "content": _render_graph_summary(graph),
                        "metadata": graph,
                    }
                )
        except Exception as e:
            warnings.append(f"Neo4j lookup failed: {e}")
    else:
        warnings.append("Neo4j not configured; relationship personalization is limited")

    # Pinecone semantic evidence
    emb_provider = (embedding_provider or "").strip().lower()
    if pinecone and (openai_embed_fn or emb_provider == "postgres"):
        try:
            query_text = _build_semantic_query_text(person=person, projects=projects, month=resolved_month)
            query_embedding: Optional[List[float]] = None

            if openai_embed_fn:
                query_embedding = await openai_embed_fn(query_text)
            elif emb_provider == "postgres":
                # Use an existing embedding for this person from Postgres (pgvector stored as text via asyncpg).
                # This enables Pinecone retrieval without needing OpenAI embeddings.
                query_embedding = await _fetch_person_embedding_from_postgres(
                    postgres_pool,
                    employee_id=employee_id,
                    email=email or person.get("email"),
                )

            if not query_embedding:
                raise RuntimeError(
                    "No query embedding available. For EMBEDDING_PROVIDER=postgres, provide person.email (or an employee_id that exists in employees table)."
                )

            md_filter: Dict[str, Any] = {}
            # If your vectors store email, this helps scope retrieval.
            if person.get("email"):
                md_filter["email"] = {"$eq": str(person["email"]).lower()}

            # Query project docs (usually the most useful evidence for monthly reviews)
            proj_matches = pinecone.query_person_evidence(
                namespace=pinecone_namespace_project_docs,
                query_embedding=query_embedding,
                top_k=top_k,
                metadata_filter=None,
            )

            # Optionally also query developer profiles (helpful if you want "similar peers" signals)
            prof_matches = pinecone.query_person_evidence(
                namespace=pinecone_namespace_developer_profiles,
                query_embedding=query_embedding,
                top_k=min(5, top_k),
                metadata_filter=md_filter or None,
            )

            if proj_matches or prof_matches:
                lines: List[str] = []
                for m in proj_matches[:top_k]:
                    md = m.get("metadata") or {}
                    title = md.get("title") or md.get("source_title") or m.get("id")
                    snippet = (md.get("content") or md.get("text") or "").strip().replace("\n", " ")
                    if len(snippet) > 240:
                        snippet = snippet[:240] + "…"
                    lines.append(f"[project_doc] score={m['score']:.3f} {title} — {snippet}")
                for m in prof_matches[:5]:
                    md = m.get("metadata") or {}
                    title = md.get("title") or m.get("id")
                    lines.append(f"[developer_profile] score={m['score']:.3f} {title}")

                evidence.append(
                    {
                        "source": "pinecone",
                        "title": "Semantic memory (Pinecone)",
                        "content": "\n".join(lines) if lines else "(no matches)",
                        "metadata": {"project_docs": proj_matches[:top_k], "developer_profiles": prof_matches[:5]},
                    }
                )
        except Exception as e:
            warnings.append(f"Pinecone retrieval failed: {e}")
    elif not pinecone:
        warnings.append("Pinecone not configured; semantic personalization is limited")
    else:
        warnings.append("Embeddings not configured; skipping Pinecone semantic retrieval")

    person_out = dict(person)
    if projects:
        person_out["projects"] = projects

    return BuiltContext(person=person_out, month=resolved_month, evidence=evidence, warnings=warnings)


def _build_semantic_query_text(*, person: Dict[str, Any], projects: List[Dict[str, Any]], month: str) -> str:
    bits: List[str] = [f"Monthly review evidence for {month}."]
    if person.get("name"):
        bits.append(f"Employee name: {person['name']}")
    if person.get("email"):
        bits.append(f"Employee email: {person['email']}")
    if person.get("role"):
        bits.append(f"Role: {person['role']}")
    if person.get("team_name"):
        bits.append(f"Team: {person['team_name']}")
    if projects:
        bits.append("Projects: " + ", ".join([p.get("name") or "(unknown)" for p in projects[:8]]))
    bits.append("Focus: accomplishments, blockers, collaboration, growth, goals, feedback.")
    return "\n".join(bits)


def _render_graph_summary(graph: Dict[str, Any]) -> str:
    projects = [p.get("name") for p in (graph.get("projects") or []) if p.get("name")]
    skills = [s.get("name") for s in (graph.get("skills") or []) if s.get("name")]
    teams = [t.get("name") for t in (graph.get("teams") or []) if t.get("name")]
    parts: List[str] = []
    if teams:
        parts.append("Teams: " + ", ".join(teams[:5]))
    if projects:
        parts.append("Graph projects: " + ", ".join(projects[:8]))
    if skills:
        parts.append("Skills: " + ", ".join(skills[:10]))
    return "\n".join(parts) if parts else "No graph context found"


def _parse_pgvector_text(vec_text: str) -> List[float]:
    t = (vec_text or "").strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1]
    if not t:
        return []
    return [float(x) for x in t.split(",") if x.strip()]


async def _fetch_person_embedding_from_postgres(postgres_pool, *, employee_id: Optional[str], email: Optional[str]) -> Optional[List[float]]:
    if not postgres_pool:
        return None

    resolved_email: Optional[str] = (email or "").strip() or None
    resolved_employee_id: Optional[str] = (employee_id or "").strip() or None

    async with postgres_pool.acquire() as conn:
        # If only a numeric employee_id is provided, try mapping it to an email first.
        if not resolved_email and resolved_employee_id and resolved_employee_id.isdigit():
            try:
                resolved_email = await conn.fetchval(
                    "SELECT email FROM employees WHERE id = $1::int LIMIT 1",
                    int(resolved_employee_id),
                )
            except Exception:
                resolved_email = None

        if not resolved_email:
            return None

        row = await conn.fetchrow(
            """
            SELECT embedding
            FROM embeddings
            WHERE source_table = 'employees'
              AND lower(metadata->>'email') = lower($1)
              AND embedding IS NOT NULL
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """,
            resolved_email,
        )
        if not row:
            return None
        try:
            vec = _parse_pgvector_text(str(row["embedding"]))
            return vec or None
        except Exception:
            return None
