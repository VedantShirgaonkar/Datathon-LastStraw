from __future__ import annotations

import uuid
from typing import List, Tuple

from hr_voice_agent.services.session_store import InMemorySessionStore, SessionState


def create_session(*, store: InMemorySessionStore, person: dict, month: str, questions: List[str]) -> SessionState:
    session_id = str(uuid.uuid4())
    state = SessionState(session_id=session_id, person=person, month=month, questions=questions, asked_idx=0, summary="")
    store.put(state)
    return state


def apply_turn(*, store: InMemorySessionStore, session_id: str, transcript_text: str) -> Tuple[str, str, bool]:
    state = store.get(session_id)
    if not state:
        raise KeyError("session not found")

    t = (transcript_text or "").strip()
    if t:
        # Minimal, safe running summary. (LLM summarization can be added later.)
        state.summary = (state.summary + " " + t).strip()

    # Move to next question only after we received an answer.
    if state.asked_idx < len(state.questions) - 1:
        state.asked_idx += 1
        return state.questions[state.asked_idx], state.summary, False

    return "Thanks — that’s all my questions for this month.", state.summary, True
