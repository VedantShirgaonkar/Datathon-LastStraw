"""
Enhanced Logging Configuration for Engineering Intelligence Platform
=====================================================================
Provides:
- Structured JSON logging for production / human-readable colored console logs for dev
- Correlation IDs for request tracing across agents and tools
- File-based logging with daily rotation
- Phase timing, tool call logging, LLM call logging, agent decision logging
- Configurable log levels per component
"""

import logging
import logging.handlers
import json
import os
import sys
import uuid
import time
import threading
from datetime import datetime
from typing import Optional, Any
from contextlib import contextmanager


# ============================================================================
# Correlation ID management (thread-local)
# ============================================================================

_local = threading.local()


def get_correlation_id() -> str:
    """Get the current correlation ID for this thread, or create one."""
    cid = getattr(_local, "correlation_id", None)
    if cid is None:
        cid = str(uuid.uuid4())[:8]
        _local.correlation_id = cid
    return cid


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set a new correlation ID for this request/thread. Returns the ID."""
    cid = cid or str(uuid.uuid4())[:8]
    _local.correlation_id = cid
    return cid


def clear_correlation_id():
    """Clear the correlation ID after a request completes."""
    _local.correlation_id = None


# ============================================================================
# Custom Formatters
# ============================================================================

class ColoredConsoleFormatter(logging.Formatter):
    """Human-readable colored formatter for console (dev mode)."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        component = getattr(record, "component", "SYSTEM")
        phase = getattr(record, "phase", "")
        cid = getattr(record, "correlation_id", "")

        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        parts = [f"{color}[{ts}]", f"[{record.levelname:<7}]", f"[{component}]"]
        if cid:
            parts.append(f"[{cid}]")
        if phase:
            parts.append(f"[{phase}]")
        parts.append(f"{self.RESET}")

        prefix = " ".join(parts)
        return f"{prefix} {record.getMessage()}"


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for file logging / production."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "component": getattr(record, "component", "SYSTEM"),
            "correlation_id": getattr(record, "correlation_id", ""),
            "phase": getattr(record, "phase", ""),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


# ============================================================================
# Correlation-injecting Filter
# ============================================================================

class CorrelationFilter(logging.Filter):
    """Injects the thread-local correlation ID into every log record."""

    def filter(self, record):
        record.correlation_id = get_correlation_id()
        if not hasattr(record, "component"):
            record.component = "SYSTEM"
        if not hasattr(record, "phase"):
            record.phase = ""
        return True


# ============================================================================
# Logger Factory
# ============================================================================

_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
)
_configured_root = False


def _ensure_root_configured():
    """Configure the root logger once with file + console handlers."""
    global _configured_root
    if _configured_root:
        return
    _configured_root = True

    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler (colored, INFO+)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(ColoredConsoleFormatter())
    console.addFilter(CorrelationFilter())
    root.addHandler(console)

    # File handler (JSON, DEBUG+, daily rotation, 7 days)
    log_path = os.path.join(_LOG_DIR, "agent_system.log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    file_handler.addFilter(CorrelationFilter())
    root.addHandler(file_handler)

    # Error-only file (JSON, ERROR+, 30 days)
    error_path = os.path.join(_LOG_DIR, "errors.log")
    error_handler = logging.handlers.TimedRotatingFileHandler(
        error_path, when="midnight", backupCount=30, encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    error_handler.addFilter(CorrelationFilter())
    root.addHandler(error_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "neo4j", "clickhouse_connect"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str, component: Optional[str] = None, level: int = logging.DEBUG):
    """
    Get a configured logger for a specific component.

    Args:
        name:      Logger name (typically __name__)
        component: Component tag (e.g. 'POSTGRES_TOOLS', 'SUPERVISOR')
        level:     Logging level
    Returns:
        ComponentAdapter that injects component/phase into every record.
    """
    _ensure_root_configured()

    logger = logging.getLogger(name)
    logger.setLevel(level)

    class ComponentAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            kwargs.setdefault("extra", {})
            kwargs["extra"]["component"] = self.extra.get("component", "SYSTEM")
            kwargs["extra"]["phase"] = self.extra.get("phase", "")
            return msg, kwargs

    return ComponentAdapter(logger, {"component": component or name.upper()})


# ============================================================================
# Structured Logging Helpers
# ============================================================================

class PhaseLogger:
    """Context manager that logs phase start/end with elapsed time."""

    def __init__(self, logger, phase_name: str):
        self.logger = logger
        self.phase_name = phase_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        if hasattr(self.logger, "extra"):
            self.logger.extra["phase"] = self.phase_name
        self.logger.info(f"▶ Starting: {self.phase_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if exc_type:
            self.logger.error(
                f"✗ FAILED: {self.phase_name} ({elapsed:.2f}s) — {exc_type.__name__}: {exc_val}"
            )
        else:
            self.logger.info(f"✓ Completed: {self.phase_name} ({elapsed:.2f}s)")
        if hasattr(self.logger, "extra"):
            self.logger.extra["phase"] = ""
        return False


def log_tool_call(logger, tool_name: str, args: dict, result: Any = None, error: Exception = None):
    """Log a tool invocation with structured detail."""
    if error:
        logger.error(f"🔧 TOOL FAILED | {tool_name} | args={_trunc(args)} | error={error}")
    elif result is not None:
        logger.info(f"🔧 TOOL OK     | {tool_name} | args={_trunc(args)} | result={_trunc(result)}")
    else:
        logger.debug(f"🔧 TOOL CALL   | {tool_name} | args={_trunc(args)}")


def log_agent_decision(logger, agent_name: str, decision: str, context: dict = None):
    """Log an agent's routing or reasoning decision."""
    ctx = f" | ctx={_trunc(context)}" if context else ""
    logger.info(f"🤖 DECISION | {agent_name} | {decision}{ctx}")


def log_llm_call(
    logger,
    model: str,
    prompt_preview: str,
    response_preview: str = None,
    tokens_in: int = None,
    tokens_out: int = None,
    latency_ms: float = None,
):
    """Log an LLM API call with prompt/response previews and optional metrics."""
    parts = [f"🧠 LLM | model={model}", f"prompt={_trunc(prompt_preview, 120)}"]
    if response_preview:
        parts.append(f"response={_trunc(response_preview, 150)}")
    if tokens_in is not None:
        parts.append(f"tok_in={tokens_in}")
    if tokens_out is not None:
        parts.append(f"tok_out={tokens_out}")
    if latency_ms is not None:
        parts.append(f"lat={latency_ms:.0f}ms")
    logger.debug(" | ".join(parts))


def log_embedding_call(logger, model: str, text_preview: str, dimension: int, latency_ms: float = None):
    """Log an embedding generation call."""
    parts = [f"📐 EMBED | model={model} | dim={dimension} | text={_trunc(text_preview, 80)}"]
    if latency_ms is not None:
        parts.append(f"lat={latency_ms:.0f}ms")
    logger.debug(" | ".join(parts))


def log_db_query(logger, db_type: str, query_preview: str, row_count: int = None, latency_ms: float = None):
    """Log a database query execution."""
    parts = [f"💾 DB | {db_type} | {_trunc(query_preview, 100)}"]
    if row_count is not None:
        parts.append(f"rows={row_count}")
    if latency_ms is not None:
        parts.append(f"lat={latency_ms:.0f}ms")
    logger.debug(" | ".join(parts))


# ============================================================================
# Helpers
# ============================================================================

def _trunc(obj: Any, max_len: int = 200) -> str:
    """Truncate a value for safe log display."""
    s = str(obj)
    return s if len(s) <= max_len else s[:max_len] + "…"
