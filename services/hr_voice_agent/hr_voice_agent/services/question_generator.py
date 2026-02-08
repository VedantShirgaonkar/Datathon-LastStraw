from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from hr_voice_agent.models import EvidenceItem, QuestionItem


SYSTEM_PROMPT = """You are an HR review voice agent.
You create monthly review questions that are highly personalized, respectful, and actionable.
You must avoid sensitive inferences (medical, religion, etc.).
You must ground questions in the provided context and evidence, referencing concrete work context (projects, collaboration, blockers).
"""


def build_user_prompt(*, person: Dict[str, Any], month: str, evidence: List[Dict[str, Any]]) -> str:
    person_lines: List[str] = []
    for k in ["name", "email", "role", "team_name", "id"]:
        if person.get(k):
            person_lines.append(f"{k}: {person[k]}")

    projects = person.get("projects") or []
    proj_names = [p.get("name") for p in projects if p.get("name")]

    ev_lines: List[str] = []
    for i, ev in enumerate(evidence[:12], start=1):
        ev_lines.append(f"EVIDENCE {i} ({ev.get('source')}): {ev.get('title')}\n{ev.get('content')}\n")

    return "\n".join(
        [
            f"Target month: {month}",
            "Person:",
            *person_lines,
            ("Projects: " + ", ".join(proj_names[:10])) if proj_names else "Projects: (unknown)",
            "\nEvidence:",
            *ev_lines,
            "\nTask:",
            "Generate monthly HR review questions the manager can ask this person.",
            "Include a balanced set across accomplishments, blockers, collaboration, growth, wellbeing, and next-month goals.",
            "Prefer questions that refer to known projects/relationships.",
        ]
    )


def parse_questions(payload: Dict[str, Any]) -> List[QuestionItem]:
    items = payload.get("questions")
    if not isinstance(items, list):
        return []

    out: List[QuestionItem] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            out.append(
                QuestionItem(
                    question=str(it.get("question") or "").strip(),
                    category=it.get("category"),
                    rationale=str(it.get("rationale") or "").strip(),
                    followups=[str(x).strip() for x in (it.get("followups") or []) if str(x).strip()],
                )
            )
        except Exception:
            continue

    return [q for q in out if q.question]
