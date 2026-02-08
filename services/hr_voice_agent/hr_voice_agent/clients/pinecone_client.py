from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pinecone import Pinecone
from pinecone.core.openapi.shared.exceptions import NotFoundException


@dataclass
class PineconeClient:
    api_key: str
    index_name: str

    def __post_init__(self) -> None:
        pc = Pinecone(api_key=self.api_key)
        try:
            self._index = pc.Index(self.index_name)
        except NotFoundException as e:
            # Helpful error for misconfigured index name.
            try:
                available = [i.get("name") for i in (pc.list_indexes() or []) if isinstance(i, dict)]
            except Exception:
                available = []
            msg = f"Pinecone index '{self.index_name}' not found."
            if available:
                msg += f" Available indexes for this API key: {', '.join([str(x) for x in available if x])}"
            raise RuntimeError(msg) from e

    def query_person_evidence(
        self,
        *,
        namespace: str,
        query_embedding: List[float],
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        res = self._index.query(
            namespace=namespace,
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=metadata_filter,
        )
        matches = getattr(res, "matches", None) or []
        out: List[Dict[str, Any]] = []
        for m in matches:
            md = getattr(m, "metadata", None) or {}
            out.append(
                {
                    "id": getattr(m, "id", ""),
                    "score": float(getattr(m, "score", 0.0) or 0.0),
                    "metadata": md,
                }
            )
        return out
