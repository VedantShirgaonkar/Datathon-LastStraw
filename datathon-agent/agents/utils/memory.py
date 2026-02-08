"""
Conversation Memory Manager (Feature 4.1)
Thread-based conversation persistence using LangGraph checkpointers.
Provides:
  - Thread ID management
  - In-memory conversation storage (MemorySaver)
  - Context window management (trimming old messages)
  - Thread listing and cleanup
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver

from agents.utils.logger import get_logger

logger = get_logger(__name__, "MEMORY")


# ============================================================================
# Thread Manager
# ============================================================================

class ThreadInfo:
    """Metadata about a conversation thread."""

    __slots__ = ("thread_id", "title", "created_at", "last_active", "message_count")

    def __init__(self, thread_id: str, title: str = ""):
        self.thread_id = thread_id
        self.title = title
        self.created_at = datetime.now(timezone.utc)
        self.last_active = self.created_at
        self.message_count = 0

    def touch(self, msg_count: int = 0):
        self.last_active = datetime.now(timezone.utc)
        self.message_count = msg_count

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "message_count": self.message_count,
        }


class ConversationMemory:
    """
    Manages conversation threads and the LangGraph checkpointer.

    Usage:
        memory = get_conversation_memory()
        thread_id = memory.new_thread("DORA analysis")
        config = memory.get_config(thread_id)
        # Pass `config` to graph.invoke(state, config=config)
    """

    def __init__(self, max_threads: int = 50):
        self._checkpointer = MemorySaver()
        self._threads: dict[str, ThreadInfo] = {}
        self._max_threads = max_threads
        logger.info("ConversationMemory initialised (in-memory checkpointer)")

    # ── Checkpointer access ─────────────────────────────────

    @property
    def checkpointer(self) -> MemorySaver:
        """The LangGraph-compatible checkpointer."""
        return self._checkpointer

    # ── Thread management ───────────────────────────────────

    def new_thread(self, title: str = "") -> str:
        """Create a new conversation thread and return its ID."""
        thread_id = uuid.uuid4().hex[:12]
        info = ThreadInfo(thread_id, title=title or f"Thread {len(self._threads) + 1}")
        self._threads[thread_id] = info
        logger.info(f"New thread: {thread_id} — '{info.title}'")

        # Evict oldest if over limit
        self._evict_old_threads()
        return thread_id

    def get_config(self, thread_id: str) -> dict:
        """
        Build the LangGraph `config` dict for a thread.
        This is passed to `graph.invoke(state, config=config)`.
        """
        if thread_id not in self._threads:
            # Auto-create thread if referenced but not tracked
            self._threads[thread_id] = ThreadInfo(thread_id, title="Auto-created")
            logger.debug(f"Auto-created thread: {thread_id}")

        return {"configurable": {"thread_id": thread_id}}

    def touch_thread(self, thread_id: str, message_count: int = 0):
        """Update last-active timestamp and message count."""
        info = self._threads.get(thread_id)
        if info:
            info.touch(message_count)

    def list_threads(self) -> list[dict]:
        """List all threads sorted by last_active (newest first)."""
        return [
            t.to_dict()
            for t in sorted(
                self._threads.values(),
                key=lambda t: t.last_active,
                reverse=True,
            )
        ]

    def delete_thread(self, thread_id: str) -> bool:
        """Remove a thread."""
        if thread_id in self._threads:
            del self._threads[thread_id]
            logger.info(f"Deleted thread: {thread_id}")
            return True
        return False

    # ── Context window management ───────────────────────────

    @staticmethod
    def trim_messages(messages: list, max_messages: int = 20) -> list:
        """
        Trim conversation history to stay within context window.
        Keeps the system message (if any) + the last `max_messages` messages.
        """
        if len(messages) <= max_messages:
            return messages

        # Preserve any system messages at the start
        system_msgs = [m for m in messages[:3] if getattr(m, "type", "") == "system"]
        non_system = [m for m in messages if getattr(m, "type", "") != "system"]

        trimmed = system_msgs + non_system[-(max_messages - len(system_msgs)):]
        logger.debug(f"Trimmed messages: {len(messages)} → {len(trimmed)}")
        return trimmed

    # ── Internal helpers ────────────────────────────────────

    def _evict_old_threads(self):
        """Remove oldest threads if over the limit."""
        if len(self._threads) <= self._max_threads:
            return
        sorted_threads = sorted(
            self._threads.values(), key=lambda t: t.last_active
        )
        to_remove = len(self._threads) - self._max_threads
        for t in sorted_threads[:to_remove]:
            del self._threads[t.thread_id]
            logger.debug(f"Evicted old thread: {t.thread_id}")


# ============================================================================
# Singleton
# ============================================================================

_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get the singleton ConversationMemory instance."""
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
