from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class PersonRef(BaseModel):
    employee_id: Optional[str] = Field(default=None, description="Internal UUID/string id")
    email: Optional[str] = Field(default=None)


class MonthlyReviewQuestionsRequest(BaseModel):
    person: PersonRef
    month: Optional[str] = Field(
        default=None,
        description="Target month as YYYY-MM. If omitted, service uses current month.",
    )
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    max_questions: Optional[int] = Field(default=None, ge=3, le=20)


class EvidenceItem(BaseModel):
    source: Literal["postgres", "neo4j", "pinecone"]
    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QuestionItem(BaseModel):
    question: str
    category: Literal[
        "accomplishments",
        "goals",
        "blockers",
        "collaboration",
        "growth",
        "wellbeing",
        "feedback",
        "alignment",
    ]
    rationale: str
    followups: List[str] = Field(default_factory=list)


class MonthlyReviewQuestionsResponse(BaseModel):
    person: Dict[str, Any]
    month: str
    questions: List[QuestionItem]
    evidence_used: List[EvidenceItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    person: PersonRef
    month: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    first_question: str
    month: str
    person: Dict[str, Any]


class SessionTurnRequest(BaseModel):
    transcript_text: str = Field(description="User's spoken text (already transcribed)")


class SessionTurnResponse(BaseModel):
    session_id: str
    assistant_question: str
    running_summary: str
    done: bool


class TTSRequest(BaseModel):
    text: str

