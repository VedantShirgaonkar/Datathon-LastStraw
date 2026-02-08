from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from pinecone import Pinecone
from pinecone.core.openapi.shared.exceptions import NotFoundException

from hr_voice_agent.config import get_settings


def _parse_pgvector_text(vec_text: str) -> List[float]:
    t = (vec_text or "").strip()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1]
    if not t:
        return []
    return [float(x) for x in t.split(",") if x.strip()]


def _safe_metadata(md: Dict[str, Any], *, max_text: int = 2500) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (md or {}).items():
        # Pinecone metadata must be JSON-serializable.
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool, list, dict)):
            out[k] = v
        else:
            out[k] = str(v)

    # Keep metadata payload small-ish.
    for k in ["content", "text"]:
        if k in out and isinstance(out[k], str) and len(out[k]) > max_text:
            out[k] = out[k][:max_text] + "…"

    return out


def _namespace_for_embedding_type(settings, embedding_type: str) -> str:
    et = (embedding_type or "").strip().lower()
    if et in {"project_doc", "project", "project_overview"}:
        return settings.pinecone_namespace_project_docs
    return settings.pinecone_namespace_developer_profiles


async def _fetch_embeddings_rows(conn: asyncpg.Connection, *, limit: int, where_sql: str, where_args: Tuple[Any, ...]) -> List[asyncpg.Record]:
    sql = (
        "SELECT id, embedding_type, source_table, source_id, title, content, metadata, embedding "
        "FROM embeddings "
        + where_sql
        + " ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST "
        + f" LIMIT {int(limit)}"
    )
    return await conn.fetch(sql, *where_args)


async def _main() -> int:
    s = get_settings()

    ap = argparse.ArgumentParser(description="Sync Postgres `embeddings` rows into Pinecone namespaces")
    ap.add_argument("--limit", type=int, default=500, help="Max embeddings rows to sync")
    ap.add_argument(
        "--embedding-type",
        type=str,
        default="",
        help="Optional filter, e.g. developer_profile or project_doc",
    )
    ap.add_argument(
        "--source-table",
        type=str,
        default="",
        help="Optional filter, e.g. employees or projects",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be upserted without writing to Pinecone",
    )
    args = ap.parse_args()

    if not s.postgres_enabled():
        raise SystemExit("POSTGRES_DSN not configured")
    if not s.pinecone_enabled():
        raise SystemExit("PINECONE_API_KEY / PINECONE_INDEX not configured")

    pc = Pinecone(api_key=s.pinecone_api_key)
    try:
        index = pc.Index(s.pinecone_index)
    except NotFoundException as e:
        available = []
        try:
            available = [i.get("name") for i in (pc.list_indexes() or []) if isinstance(i, dict)]
        except Exception:
            available = []
        hint = ""
        if available:
            hint = " Available indexes: " + ", ".join([str(x) for x in available if x])
        raise SystemExit(f"PINECONE_INDEX '{s.pinecone_index}' not found for this API key.{hint}") from e

    conn = await asyncpg.connect(dsn=s.postgres_dsn)
    try:
        where: List[str] = ["WHERE embedding IS NOT NULL"]
        where_args: List[Any] = []

        if args.embedding_type:
            where.append(f"AND lower(embedding_type) = lower(${len(where_args)+1})")
            where_args.append(args.embedding_type)

        if args.source_table:
            where.append(f"AND lower(source_table) = lower(${len(where_args)+1})")
            where_args.append(args.source_table)

        where_sql = " " + " ".join(where)
        rows = await _fetch_embeddings_rows(conn, limit=int(args.limit), where_sql=where_sql, where_args=tuple(where_args))

        total = len(rows)
        if total == 0:
            print("No rows matched.")
            return 0

        # Build upserts grouped by namespace.
        batches: Dict[str, List[Dict[str, Any]]] = {}
        dims: Optional[int] = None

        for r in rows:
            vec = _parse_pgvector_text(str(r["embedding"]))
            if not vec:
                continue
            if dims is None:
                dims = len(vec)
            elif len(vec) != dims:
                # Skip inconsistent vectors to avoid Pinecone errors.
                continue

            embedding_type = str(r["embedding_type"] or "")
            ns = _namespace_for_embedding_type(s, embedding_type)

            metadata: Dict[str, Any] = {
                "embedding_type": embedding_type,
                "source_table": str(r["source_table"] or ""),
                "source_id": str(r["source_id"] or ""),
                "title": str(r["title"] or ""),
                "content": str(r["content"] or ""),
            }
            # Preserve any structured metadata too.
            try:
                metadata["metadata"] = r["metadata"]
            except Exception:
                pass

            item = {
                "id": f"pg:{r['id']}",
                "values": vec,
                "metadata": _safe_metadata(metadata),
            }
            batches.setdefault(ns, []).append(item)

        if args.dry_run:
            for ns, items in batches.items():
                print(f"namespace={ns} upserts={len(items)}")
                if items:
                    print("  sample:", {k: items[0][k] for k in ["id", "metadata"]})
            return 0

        # Upsert.
        for ns, items in batches.items():
            if not items:
                continue
            print(f"Upserting {len(items)} vectors into namespace={ns} …")
            index.upsert(vectors=items, namespace=ns, batch_size=100, show_progress=True)

        print("Done.")
        return 0
    finally:
        await conn.close()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
