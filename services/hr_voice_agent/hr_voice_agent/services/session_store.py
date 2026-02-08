from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SessionState:
    session_id: str
    person: dict
    month: str
    questions: List[str]
    asked_idx: int = 0
    summary: str = ""


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def put(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)
