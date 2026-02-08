"""
Multi-Model Router
Classifies incoming tasks and selects the optimal LLM for each.

Model specializations:
  - Qwen 2.5 72B:   Complex reasoning, planning, executive summaries
  - Llama 3.1 70B:  Analytics, long-context analysis, historical comparison
  - Hermes 3 8B:    Fast classification, quick lookups, parallel workers
  - DeepSeek Coder: SQL/Cypher generation, code analysis, technical diagnosis
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from agents.utils.config import get_config
from agents.utils.logger import get_logger

logger = get_logger(__name__, "MODEL_ROUTER")


# ============================================================================
# Task Categories
# ============================================================================

class TaskType(str, Enum):
    """Categories of tasks the system handles."""
    CODE_ANALYSIS = "code_analysis"
    ANALYTICS = "analytics"
    PLANNING = "planning"
    QUICK_LOOKUP = "quick_lookup"
    GENERAL = "general"


# ============================================================================
# Model Selection Result
# ============================================================================

@dataclass
class ModelSelection:
    """Result of model routing — which model to use and why."""
    model_name: str        # Full model identifier (e.g. "Qwen/Qwen2.5-72B-Instruct")
    display_name: str      # Short name for UI (e.g. "Qwen 72B")
    task_type: TaskType    # Classified task type
    reason: str            # Why this model was selected
    temperature: float     # Recommended temperature for the task

    @property
    def emoji(self) -> str:
        """UI emoji for the model."""
        return _MODEL_EMOJI.get(self.task_type, "🤖")


_MODEL_EMOJI = {
    TaskType.CODE_ANALYSIS: "💻",
    TaskType.ANALYTICS: "📊",
    TaskType.PLANNING: "🧠",
    TaskType.QUICK_LOOKUP: "⚡",
    TaskType.GENERAL: "🤖",
}


# ============================================================================
# Keyword-based Task Classifier
# ============================================================================

# Patterns are checked in order; first match wins.
# Each entry: (TaskType, compiled regex, description)
_CLASSIFICATION_RULES: list[tuple[TaskType, re.Pattern, str]] = [
    # ── Code / SQL / Technical (checked first for explicit SQL/code keywords) ──
    (
        TaskType.CODE_ANALYSIS,
        re.compile(
            r"\b(sql|cypher|generate\s+(a\s+)?query|write\s+(a\s+)?query|"
            r"code\b|schema|migrat|refactor|debug|"
            r"syntax|compil|ci[\s/]?cd|build\s?(pipeline|fail)|deploy\s?(script|pipeline)|"
            r"git\s?diff|pull\s?request|pr\s?review|lint|test\s?case)",
            re.IGNORECASE,
        ),
        "Code / SQL / technical task detected",
    ),
    # ── Analytics / Metrics ─────────────────────────────────
    (
        TaskType.ANALYTICS,
        re.compile(
            r"\b(dora|metric|deploy|lead\s?time|failure\s?rate|mttr|"
            r"velocity|throughput|trend|anomal|spike|regression|"
            r"frequency|change\s?failure|recovery|burndown|"
            r"sprint\s?report|week[\s-]?over[\s-]?week|month[\s-]?over[\s-]?month|"
            r"comparison|benchmark|percentile|statistic|aggregat|"
            r"activity|event\b|commit|log\s?analy)",
            re.IGNORECASE,
        ),
        "Analytics / metrics task detected",
    ),
    # ── Planning / Reasoning ────────────────────────────────
    (
        TaskType.PLANNING,
        re.compile(
            r"\b(plan\b|allocat|capacity|workload|over[\s-]?alloc|bottleneck|"
            r"risk\b|priorit|deadline|resource|budget|roadmap|"
            r"recommend|suggest|strateg|trade[\s-]?off|"
            r"rebalanc|reschedul|optimiz|staffing|"
            r"1[:\s-]?1|one[\s-]?on[\s-]?one|prep\s?(for|my)|meeting\s?prep|"
            r"talking\s?point|briefing)",
            re.IGNORECASE,
        ),
        "Planning / complex reasoning task detected",
    ),
    # ── Quick Lookup (people / profiles / skills / expert discovery) ──
    (
        TaskType.QUICK_LOOKUP,
        re.compile(
            r"\b(who\s+is|who\s+does|who\s+works|who\s+collaborat|who\s+can\s+help|"
            r"list\s+(all|the)\s+(developer|member|engineer|team)|"
            r"find\s+(me\s+)?(a|an)?\s*(developer|expert)|"
            r"what\s+team|get\s+profile|contact|email\b|"
            r"skill|expertise|collaborat|know[s]?\s+about|"
            r"expert\s+(in|on|for|with|at)|graph\s?rag|"
            r"team\s+member|org\s?chart)",
            re.IGNORECASE,
        ),
        "Quick lookup / profile / expert query detected",
    ),
]


def classify_task(query: str) -> tuple[TaskType, str]:
    """
    Classify a user query into a TaskType.

    Returns:
        (task_type, reason) tuple.
    """
    for task_type, pattern, reason in _CLASSIFICATION_RULES:
        if pattern.search(query):
            logger.debug(f"Task classified as {task_type.value}: {reason}")
            return task_type, reason

    logger.debug("No specific pattern matched — defaulting to GENERAL")
    return TaskType.GENERAL, "No specific pattern matched — using general-purpose model"


# ============================================================================
# Model Selector
# ============================================================================

def select_model(task_type: TaskType) -> ModelSelection:
    """
    Given a task type, return the optimal model configuration.
    """
    config = get_config()
    f = config.featherless

    routing_table: dict[TaskType, ModelSelection] = {
        TaskType.CODE_ANALYSIS: ModelSelection(
            model_name=f.model_code,
            display_name="DeepSeek Coder V2",
            task_type=TaskType.CODE_ANALYSIS,
            reason="Code-specialised model for SQL/Cypher generation and technical analysis",
            temperature=0.0,
        ),
        TaskType.ANALYTICS: ModelSelection(
            model_name=f.model_analytics,
            display_name="Llama 3.1 70B",
            task_type=TaskType.ANALYTICS,
            reason="Strong long-context analytics model for metrics and trend analysis",
            temperature=0.1,
        ),
        TaskType.PLANNING: ModelSelection(
            model_name=f.model_primary,
            display_name="Qwen 72B",
            task_type=TaskType.PLANNING,
            reason="Top-tier reasoning model for complex planning and resource optimisation",
            temperature=0.1,
        ),
        TaskType.QUICK_LOOKUP: ModelSelection(
            model_name=f.model_fast,
            display_name="Hermes 3 8B",
            task_type=TaskType.QUICK_LOOKUP,
            reason="Lightweight model for fast profile lookups and simple queries",
            temperature=0.1,
        ),
        TaskType.GENERAL: ModelSelection(
            model_name=f.model_primary,
            display_name="Qwen 72B",
            task_type=TaskType.GENERAL,
            reason="General-purpose model for unclassified queries",
            temperature=0.1,
        ),
    }

    selection = routing_table[task_type]
    logger.info(
        f"Model selected: {selection.display_name} "
        f"(task={task_type.value}, reason={selection.reason})"
    )
    return selection


def route_query(query: str) -> ModelSelection:
    """
    End-to-end: classify the query and pick the optimal model.
    This is the main entry point used by the supervisor.
    """
    task_type, reason = classify_task(query)
    selection = select_model(task_type)
    return selection
