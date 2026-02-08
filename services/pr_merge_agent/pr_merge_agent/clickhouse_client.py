from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import clickhouse_connect

from pr_merge_agent.config import Settings


@dataclass(frozen=True)
class PendingPr:
    repo: str
    pr_number: int
    project_id: str


class ClickHouseClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_username,
            password=settings.clickhouse_password,
            secure=settings.clickhouse_secure,
            database=settings.clickhouse_database,
        )

    @property
    def table(self) -> str:
        return self._settings.clickhouse_events_table

    def select_scalar(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        result = self._client.query(query, parameters=params or {})
        if not result.result_rows:
            return None
        return result.result_rows[0][0]

    def query_rows(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple[Any, ...]]:
        result = self._client.query(query, parameters=params or {})
        return list(result.result_rows)

    def has_pr_merged_event(self, repo: str, pr_number: int, merged_event_type: str) -> bool:
        entity_id = self._entity_id(repo, pr_number)
        q = (
            f"SELECT count() FROM {self.table} "
            "WHERE source = 'github' AND event_type = {merged_event_type:String} AND entity_id = {entity_id:String}"
        )
        count = self.select_scalar(q, {"merged_event_type": merged_event_type, "entity_id": entity_id})
        return bool(count and int(count) > 0)

    def recently_emailed(self, repo: str, pr_number: int, dedupe_minutes: int) -> bool:
        entity_id = self._entity_id(repo, pr_number)
        q = (
            f"SELECT count() FROM {self.table} "
            "WHERE source = 'pr_merge_agent' AND event_type = 'pr_merge_email_sent' "
            "AND entity_id = {entity_id:String} "
            "AND timestamp > now() - INTERVAL {mins:UInt32} MINUTE"
        )
        count = self.select_scalar(q, {"entity_id": entity_id, "mins": int(dedupe_minutes)})
        return bool(count and int(count) > 0)

    def insert_event(
        self,
        *,
        source: str,
        event_type: str,
        project_id: str,
        actor_id: str,
        entity_id: str,
        entity_type: str,
        metadata: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        row = [
            str(uuid.uuid4()),
            ts,
            source,
            event_type,
            project_id,
            actor_id,
            entity_id,
            entity_type,
            json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
        ]
        self._client.insert(
            self.table,
            [row],
            column_names=[
                "event_id",
                "timestamp",
                "source",
                "event_type",
                "project_id",
                "actor_id",
                "entity_id",
                "entity_type",
                "metadata",
            ],
        )

    def pending_prs_from_events(self, open_event_types: Sequence[str], merged_event_type: str) -> List[PendingPr]:
        """Best-effort: expects PR open events to store repo/pr_number in metadata."""
        table = self.table
        q = """
        WITH opened AS (
            SELECT
                project_id,
                entity_id,
                any(metadata) AS metadata
            FROM """ + table + """
            WHERE source = 'github' AND event_type IN {open_event_types:Array(String)}
            GROUP BY project_id, entity_id
        ), merged AS (
            SELECT project_id, entity_id
            FROM """ + table + """
            WHERE source = 'github' AND event_type = {merged_event_type:String}
            GROUP BY project_id, entity_id
        )
        SELECT opened.project_id, opened.entity_id, opened.metadata
        FROM opened
        LEFT JOIN merged USING (project_id, entity_id)
        WHERE merged.entity_id IS NULL
        """
        rows = self.query_rows(q, {"open_event_types": list(open_event_types), "merged_event_type": merged_event_type})
        pending: List[PendingPr] = []
        for project_id, entity_id, metadata_str in rows:
            try:
                md = json.loads(metadata_str) if metadata_str else {}
            except Exception:
                md = {}
            repo = (md.get("repo") or md.get("repository") or md.get("repo_full_name") or "").strip()
            pr_number = md.get("pr_number") or md.get("number")
            if not repo or not pr_number:
                continue
            try:
                pending.append(PendingPr(repo=repo, pr_number=int(pr_number), project_id=str(project_id)))
            except Exception:
                continue
        return pending

    @staticmethod
    def _entity_id(repo: str, pr_number: int) -> str:
        return f"pr:{repo}#{pr_number}"
