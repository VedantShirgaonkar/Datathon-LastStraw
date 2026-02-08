"""
Streaming Utilities for Engineering Intelligence Platform
==========================================================
Provides:
- Typed streaming event protocol for consistent event shapes
- StreamCallbackHandler that intercepts LangChain/LangGraph callbacks
  and emits structured events (token, tool_start, tool_end, routing, etc.)
- AsyncStreamBuffer for collecting events across threads
- Console renderer for interactive CLI streaming
- SSE formatter for future HTTP/WebSocket frontends

Feature 4.2 — Streaming Responses with Tool Call Visualization
"""

from __future__ import annotations

import time
import json
import queue
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Union,
)

from agents.utils.logger import get_logger

logger = get_logger(__name__, "STREAMING")


# ============================================================================
# Event Types
# ============================================================================

class StreamEventType(str, Enum):
    """All possible streaming event types."""
    # ── Meta / lifecycle ──
    STREAM_START = "stream_start"
    STREAM_END = "stream_end"

    # ── Routing ──
    ROUTING = "routing"
    MODEL_SELECTION = "model_selection"

    # ── Token-level LLM output ──
    TOKEN = "token"                      # single token from the LLM

    # ── Tool invocation ──
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"

    # ── Agent lifecycle ──
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"

    # ── Final assembled response ──
    RESPONSE = "response"

    # ── Error ──
    ERROR = "error"

    # ── Progress / status ──
    STATUS = "status"


@dataclass
class StreamEvent:
    """
    A single streaming event emitted to the consumer.

    Attributes:
        event_type:   The kind of event (token, tool_start, …)
        data:         Payload — meaning depends on event_type
        timestamp:    Unix epoch when the event was created
        metadata:     Extra context (model name, tool args, …)
    """
    event_type: StreamEventType
    data: Any = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Convenience factories ───────────────────────────────

    @classmethod
    def stream_start(cls, query: str, thread_id: str = "") -> "StreamEvent":
        return cls(
            event_type=StreamEventType.STREAM_START,
            data={"query": query, "thread_id": thread_id},
        )

    @classmethod
    def stream_end(cls, total_tokens: int = 0, elapsed_s: float = 0) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.STREAM_END,
            data={"total_tokens": total_tokens, "elapsed_s": round(elapsed_s, 2)},
        )

    @classmethod
    def routing(cls, agent: str) -> "StreamEvent":
        return cls(event_type=StreamEventType.ROUTING, data={"agent": agent})

    @classmethod
    def model_selection(
        cls,
        model: str,
        emoji: str = "🤖",
        task_type: str = "",
        reason: str = "",
    ) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.MODEL_SELECTION,
            data={
                "model": model,
                "emoji": emoji,
                "task_type": task_type,
                "reason": reason,
            },
        )

    @classmethod
    def token(cls, text: str, agent: str = "") -> "StreamEvent":
        return cls(
            event_type=StreamEventType.TOKEN,
            data={"text": text},
            metadata={"agent": agent},
        )

    @classmethod
    def tool_start(cls, tool_name: str, args: Dict[str, Any] = None) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.TOOL_START,
            data={"tool": tool_name, "args": _safe_trunc_dict(args or {})},
        )

    @classmethod
    def tool_end(
        cls,
        tool_name: str,
        result_preview: str = "",
        elapsed_s: float = 0,
    ) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.TOOL_END,
            data={
                "tool": tool_name,
                "result_preview": result_preview[:200],
                "elapsed_s": round(elapsed_s, 2),
            },
        )

    @classmethod
    def agent_start(cls, agent: str, model: str = "") -> "StreamEvent":
        return cls(
            event_type=StreamEventType.AGENT_START,
            data={"agent": agent, "model": model},
        )

    @classmethod
    def agent_end(cls, agent: str, elapsed_s: float = 0) -> "StreamEvent":
        return cls(
            event_type=StreamEventType.AGENT_END,
            data={"agent": agent, "elapsed_s": round(elapsed_s, 2)},
        )

    @classmethod
    def response(cls, content: str) -> "StreamEvent":
        return cls(event_type=StreamEventType.RESPONSE, data={"content": content})

    @classmethod
    def error(cls, message: str) -> "StreamEvent":
        return cls(event_type=StreamEventType.ERROR, data={"message": message})

    @classmethod
    def status(cls, message: str) -> "StreamEvent":
        return cls(event_type=StreamEventType.STATUS, data={"message": message})

    # ── Serialisation ───────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "event": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def to_sse(self) -> str:
        """Format as a Server-Sent Event string (for HTTP streaming)."""
        payload = json.dumps(self.to_dict(), default=str)
        return f"event: {self.event_type.value}\ndata: {payload}\n\n"


# ============================================================================
# Stream Buffer (thread-safe event queue)
# ============================================================================

class StreamBuffer:
    """
    Thread-safe buffer that collects StreamEvents and yields them.

    Producers call `put(event)` / `close()`.
    Consumers iterate via `events()` (blocking generator).
    """

    def __init__(self, timeout: float = 300):
        self._queue: queue.Queue[Optional[StreamEvent]] = queue.Queue()
        self._timeout = timeout
        self._closed = False
        self._token_count = 0
        self._start_time = time.time()

    # ── Producer API ────────────────────────────────────────

    def put(self, event: StreamEvent):
        if self._closed:
            return
        if event.event_type == StreamEventType.TOKEN:
            self._token_count += 1
        self._queue.put(event)

    def close(self):
        """Signal that no more events will be produced."""
        if not self._closed:
            elapsed = time.time() - self._start_time
            self.put(StreamEvent.stream_end(
                total_tokens=self._token_count,
                elapsed_s=elapsed,
            ))
            self._closed = True
            self._queue.put(None)  # sentinel

    # ── Consumer API ────────────────────────────────────────

    def events(self) -> Generator[StreamEvent, None, None]:
        """Blocking generator that yields events until the stream closes."""
        while True:
            try:
                event = self._queue.get(timeout=self._timeout)
            except queue.Empty:
                logger.warning("Stream timed out waiting for events")
                yield StreamEvent.error("Stream timed out")
                return
            if event is None:
                return
            yield event

    @property
    def token_count(self) -> int:
        return self._token_count


# ============================================================================
# Console Renderer (for interactive CLI)
# ============================================================================

# ANSI helpers
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_RESET = "\033[0m"


def render_stream_to_console(
    events: Iterator[StreamEvent],
    *,
    show_tools: bool = True,
    show_routing: bool = True,
    show_model: bool = True,
    show_tokens: bool = True,
) -> str:
    """
    Render a stream of events to the console in real-time.

    Returns the complete assembled response text.
    """
    full_response = []
    active_tools: Dict[str, float] = {}  # tool_name → start_time
    response_started = False

    for event in events:
        etype = event.event_type

        # ── Stream start ─────────────────
        if etype == StreamEventType.STREAM_START:
            pass  # silent

        # ── Model selection ──────────────
        elif etype == StreamEventType.MODEL_SELECTION and show_model:
            d = event.data or {}
            emoji = d.get("emoji", "🤖")
            model = d.get("model", "Unknown")
            task = d.get("task_type", "")
            reason = d.get("reason", "")
            print(f"\n  {emoji} {_BOLD}Using {model}{_RESET} for {task}")
            if reason:
                print(f"  {_DIM}   └─ {reason}{_RESET}")

        # ── Routing ──────────────────────
        elif etype == StreamEventType.ROUTING and show_routing:
            agent = (event.data or {}).get("agent", "?")
            print(f"  {_CYAN}↪ Routing to: {agent}{_RESET}")

        # ── Agent start/end ──────────────
        elif etype == StreamEventType.AGENT_START:
            agent = (event.data or {}).get("agent", "?")
            model = (event.data or {}).get("model", "")
            suffix = f" ({model})" if model else ""
            print(f"  {_DIM}⚙ {agent} working...{suffix}{_RESET}")

        elif etype == StreamEventType.AGENT_END:
            agent = (event.data or {}).get("agent", "?")
            elapsed = (event.data or {}).get("elapsed_s", 0)
            print(f"  {_DIM}✓ {agent} done ({elapsed:.1f}s){_RESET}")

        # ── Tool start ───────────────────
        elif etype == StreamEventType.TOOL_START and show_tools:
            d = event.data or {}
            tool = d.get("tool", "?")
            args = d.get("args", {})
            active_tools[tool] = time.time()
            emoji = _tool_emoji(tool)
            args_str = _format_tool_args(args)
            print(f"  {_YELLOW}{emoji} {tool}{_RESET}{_DIM}{args_str}{_RESET}")

        # ── Tool end ─────────────────────
        elif etype == StreamEventType.TOOL_END and show_tools:
            d = event.data or {}
            tool = d.get("tool", "?")
            elapsed = d.get("elapsed_s", 0)
            preview = d.get("result_preview", "")
            if preview:
                short = preview[:80].replace("\n", " ")
                print(f"  {_GREEN}  ✓ {tool}{_RESET} {_DIM}({elapsed:.1f}s) → {short}{_RESET}")
            else:
                print(f"  {_GREEN}  ✓ {tool}{_RESET} {_DIM}({elapsed:.1f}s){_RESET}")
            active_tools.pop(tool, None)

        # ── Token ────────────────────────
        elif etype == StreamEventType.TOKEN and show_tokens:
            text = (event.data or {}).get("text", "")
            if text:
                if not response_started:
                    print(f"\n{'─' * 50}")
                    print(f"\n{_BOLD}🤖 Response:{_RESET}\n")
                    response_started = True
                print(text, end="", flush=True)
                full_response.append(text)

        # ── Complete response (fallback) ─
        elif etype == StreamEventType.RESPONSE:
            content = (event.data or {}).get("content", "")
            if content and not full_response:
                if not response_started:
                    print(f"\n{'─' * 50}")
                    print(f"\n{_BOLD}🤖 Response:{_RESET}\n")
                    response_started = True
                print(content)
                full_response.append(content)

        # ── Status ───────────────────────
        elif etype == StreamEventType.STATUS:
            msg = (event.data or {}).get("message", "")
            print(f"  {_DIM}ℹ {msg}{_RESET}")

        # ── Error ────────────────────────
        elif etype == StreamEventType.ERROR:
            msg = (event.data or {}).get("message", "Unknown error")
            print(f"\n  ❌ {msg}")

        # ── Stream end ───────────────────
        elif etype == StreamEventType.STREAM_END:
            d = event.data or {}
            elapsed = d.get("elapsed_s", 0)
            tokens = d.get("total_tokens", 0)
            if response_started:
                print()  # newline after streaming tokens
            print(f"\n{'─' * 50}")
            stats = []
            if tokens:
                stats.append(f"{tokens} tokens")
            if elapsed:
                stats.append(f"{elapsed:.1f}s")
            if stats:
                print(f"  {_DIM}{' · '.join(stats)}{_RESET}")

    return "".join(full_response)


# ============================================================================
# SSE Formatter (for HTTP / WebSocket frontends)
# ============================================================================

def format_events_as_sse(events: Iterator[StreamEvent]) -> Generator[str, None, None]:
    """
    Convert a stream of events into SSE-formatted strings.

    Usage with FastAPI/Starlette:
        return StreamingResponse(
            format_events_as_sse(buffer.events()),
            media_type="text/event-stream",
        )
    """
    for event in events:
        yield event.to_sse()


# ============================================================================
# Helpers
# ============================================================================

_TOOL_EMOJIS = {
    "semantic_search": "🔍",
    "find_developer_by_skills": "🔍",
    "get_developer": "👤",
    "get_team": "👥",
    "list_developers": "📋",
    "get_collaborators": "🤝",
    "get_team_collaboration_graph": "🕸️",
    "find_knowledge_experts": "🎓",
    "rag_search": "📚",
    "find_expert_for_topic": "🧠",
    "quick_expert_search": "⚡",
    "natural_language_query": "💬",
    "get_dora_metrics": "📊",
    "get_deployment_metrics": "📈",
    "get_developer_activity": "📉",
    "detect_anomalies": "🚨",
    "prepare_one_on_one": "📝",
    "get_project_status": "📦",
    "get_developer_workload": "⚖️",
}


def _tool_emoji(tool_name: str) -> str:
    return _TOOL_EMOJIS.get(tool_name, "🔧")


def _format_tool_args(args: dict, max_len: int = 60) -> str:
    """Format tool args for display."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 30:
            sv = sv[:27] + "…"
        parts.append(f"{k}={sv}")
    result = " (" + ", ".join(parts) + ")"
    if len(result) > max_len:
        result = result[:max_len - 1] + "…)"
    return result


def _safe_trunc_dict(d: dict, max_val: int = 100) -> dict:
    """Truncate dict values for safe logging/display."""
    out = {}
    for k, v in d.items():
        sv = str(v)
        out[k] = sv if len(sv) <= max_val else sv[:max_val - 3] + "..."
    return out
