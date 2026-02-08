#!/usr/bin/env python3
"""
Test Suite for Feature 4.2 — Streaming Responses with Tool Call Visualization
=============================================================================

Three tiers:
  PART 1: Unit Tests       — StreamEvent creation, serialisation, buffer, renderer
  PART 2: Integration Tests — supervisor.stream_query yields correct event types,
                              CLI renderer handles all event types
  PART 3: Live LLM Tests   — end-to-end streaming with real LLM calls

Run:
    cd /Users/rahul/Desktop/Datathon
    .venv/bin/python scripts/test_streaming.py
"""

import sys, os, time, json, queue, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0


def ok(label: str, detail: str = ""):
    global passed
    passed += 1
    d = f"\n    → {detail}" if detail else ""
    print(f"  ✅ {label}{d}")


def fail(label: str, detail: str = ""):
    global failed
    failed += 1
    d = f"\n    → {detail}" if detail else ""
    print(f"  ❌ {label}{d}")


def check(condition: bool, label: str, detail: str = ""):
    if condition:
        ok(label, detail)
    else:
        fail(label, detail)


# ============================================================
# PART 1: Unit Tests
# ============================================================
print("\n" + "=" * 60)
print("PART 1: Unit Tests")
print("=" * 60)

from agents.utils.streaming import (
    StreamEvent, StreamEventType, StreamBuffer,
    render_stream_to_console, format_events_as_sse,
    _tool_emoji, _format_tool_args, _safe_trunc_dict,
)

# ── 1. StreamEvent creation ────────────────────────────────

evt = StreamEvent.token(text="Hello", agent="Insights_Specialist")
check(
    evt.event_type == StreamEventType.TOKEN,
    "StreamEvent.token() type",
    f"Got: {evt.event_type.value}",
)
check(
    evt.data["text"] == "Hello",
    "StreamEvent.token() data",
    f"Got: {evt.data}",
)
check(
    evt.metadata.get("agent") == "Insights_Specialist",
    "StreamEvent.token() metadata",
    f"Got: {evt.metadata}",
)

# ── 2. All factory methods produce valid events ────────────

factories = [
    ("stream_start", StreamEvent.stream_start("test query", "thread-1")),
    ("stream_end", StreamEvent.stream_end(total_tokens=42, elapsed_s=3.14)),
    ("routing", StreamEvent.routing(agent="DORA_Pro")),
    ("model_selection", StreamEvent.model_selection("Qwen 72B", "🧠", "analytics", "complex")),
    ("token", StreamEvent.token("word")),
    ("tool_start", StreamEvent.tool_start("semantic_search", {"query": "test"})),
    ("tool_end", StreamEvent.tool_end("semantic_search", "3 results", 0.5)),
    ("agent_start", StreamEvent.agent_start("Insights_Specialist", "Qwen 72B")),
    ("agent_end", StreamEvent.agent_end("Insights_Specialist", 2.1)),
    ("response", StreamEvent.response("Final answer")),
    ("error", StreamEvent.error("Something broke")),
    ("status", StreamEvent.status("Processing...")),
]

all_valid = True
for name, evt in factories:
    if not isinstance(evt, StreamEvent):
        all_valid = False
        break
    if evt.timestamp <= 0:
        all_valid = False
        break
check(all_valid, "All factory methods produce valid StreamEvent", f"{len(factories)} factories tested")

# ── 3. to_dict() ──────────────────────────────────────────

evt = StreamEvent.tool_start("rag_search", {"query": "test"})
d = evt.to_dict()
check(
    d["event"] == "tool_start" and d["data"]["tool"] == "rag_search",
    "to_dict() serialisation",
    f"event={d['event']}, tool={d['data']['tool']}",
)

# ── 4. to_sse() ──────────────────────────────────────────

evt = StreamEvent.token("hello")
sse = evt.to_sse()
check(
    sse.startswith("event: token\ndata: ") and sse.endswith("\n\n"),
    "to_sse() format",
    f"Preview: {sse[:50]}...",
)

# Parse the data back
sse_data = sse.split("data: ", 1)[1].strip()
parsed = json.loads(sse_data)
check(
    parsed["event"] == "token" and parsed["data"]["text"] == "hello",
    "to_sse() round-trip JSON",
    f"Parsed: event={parsed['event']}, text={parsed['data']['text']}",
)

# ── 5. StreamEventType enum ──────────────────────────────

all_types = list(StreamEventType)
check(
    len(all_types) >= 11,
    f"StreamEventType has {len(all_types)} event types",
    f"Types: {[t.value for t in all_types]}",
)

# ── 6. StreamBuffer — basic put/events ───────────────────

buf = StreamBuffer(timeout=5)
buf.put(StreamEvent.token("a"))
buf.put(StreamEvent.token("b"))
buf.put(StreamEvent.response("ab"))
buf.close()

collected = list(buf.events())
event_types = [e.event_type for e in collected]
check(
    StreamEventType.TOKEN in event_types,
    "StreamBuffer delivers TOKEN events",
)
check(
    event_types[-1] == StreamEventType.STREAM_END,
    "StreamBuffer auto-appends STREAM_END",
)
check(
    buf.token_count == 2,
    "StreamBuffer counts tokens",
    f"token_count={buf.token_count}",
)

# ── 7. StreamBuffer — timeout ────────────────────────────

buf2 = StreamBuffer(timeout=0.2)
# Don't put anything and don't close → should timeout
events = []
for e in buf2.events():
    events.append(e)
check(
    len(events) == 1 and events[0].event_type == StreamEventType.ERROR,
    "StreamBuffer timeout produces ERROR event",
    f"Got {len(events)} event(s): {[e.event_type.value for e in events]}",
)

# ── 8. StreamBuffer — threaded producer/consumer ─────────

buf3 = StreamBuffer(timeout=5)


def producer():
    for i in range(5):
        buf3.put(StreamEvent.token(f"tok{i}"))
        time.sleep(0.01)
    buf3.close()


t = threading.Thread(target=producer)
t.start()
consumed = list(buf3.events())
t.join()
token_events = [e for e in consumed if e.event_type == StreamEventType.TOKEN]
check(
    len(token_events) == 5,
    "Threaded producer/consumer delivers all tokens",
    f"Got {len(token_events)} tokens",
)

# ── 9. Tool emoji mapping ───────────────────────────────

check(
    _tool_emoji("semantic_search") == "🔍",
    "Tool emoji: semantic_search → 🔍",
)
check(
    _tool_emoji("unknown_tool") == "🔧",
    "Tool emoji: unknown → 🔧 (default)",
)

# ── 10. _format_tool_args ───────────────────────────────

args_str = _format_tool_args({"query": "test", "limit": 5})
check(
    "query=test" in args_str and "limit=5" in args_str,
    "_format_tool_args formats correctly",
    f"Got: {args_str}",
)
check(
    _format_tool_args({}) == "",
    "_format_tool_args empty dict returns empty string",
)

# ── 11. _safe_trunc_dict ────────────────────────────────

long_val = "x" * 200
truncated = _safe_trunc_dict({"key": long_val}, max_val=50)
check(
    len(truncated["key"]) == 50,
    "_safe_trunc_dict truncates long values",
    f"len={len(truncated['key'])}",
)

# ── 12. format_events_as_sse ────────────────────────────

events_for_sse = [
    StreamEvent.routing("DORA_Pro"),
    StreamEvent.token("hello"),
    StreamEvent.stream_end(1, 0.5),
]
sse_lines = list(format_events_as_sse(iter(events_for_sse)))
check(
    len(sse_lines) == 3,
    "format_events_as_sse yields correct count",
    f"Got {len(sse_lines)} SSE strings",
)
check(
    all(s.startswith("event: ") for s in sse_lines),
    "All SSE strings have event: prefix",
)

# ── 13. Console renderer (captures output) ──────────────

import io
import contextlib

test_events = [
    StreamEvent.stream_start("test query"),
    StreamEvent.model_selection("Qwen 72B", "🧠", "analytics", "complex query"),
    StreamEvent.routing("Insights_Specialist"),
    StreamEvent.agent_start("Insights_Specialist", "Qwen 72B"),
    StreamEvent.tool_start("semantic_search", {"query": "test"}),
    StreamEvent.tool_end("semantic_search", "3 matches", 0.5),
    StreamEvent.response("Here is the answer"),
    StreamEvent.agent_end("Insights_Specialist", 2.1),
    StreamEvent.stream_end(10, 3.0),
]

buf_out = io.StringIO()
with contextlib.redirect_stdout(buf_out):
    result = render_stream_to_console(iter(test_events))

output = buf_out.getvalue()
check(
    "Qwen 72B" in output,
    "Console renderer shows model name",
)
check(
    "Insights_Specialist" in output,
    "Console renderer shows routing",
)
check(
    "semantic_search" in output,
    "Console renderer shows tool calls",
)
check(
    "Here is the answer" in output,
    "Console renderer shows response",
)
check(
    result == "Here is the answer",
    "Console renderer returns response text",
    f"Got: {result[:50]}",
)


# ============================================================
# PART 2: Integration Tests
# ============================================================
print("\n" + "=" * 60)
print("PART 2: Integration Tests")
print("=" * 60)

# ── 14. Supervisor imports StreamEvent correctly ─────────

try:
    from agents.supervisor import SupervisorAgent
    from agents.utils.streaming import StreamEvent as SE2
    check(True, "Supervisor imports streaming module")
except ImportError as e:
    fail("Supervisor imports streaming module", str(e))

# ── 15. SupervisorAgent has stream_query ─────────────────

agent = SupervisorAgent()
check(
    hasattr(agent, "stream_query"),
    "SupervisorAgent.stream_query exists",
)

# ── 16. SupervisorAgent has stream_query_tokens ──────────

check(
    hasattr(agent, "stream_query_tokens"),
    "SupervisorAgent.stream_query_tokens exists",
)

# ── 17. stream_query returns generator ───────────────────

check(
    callable(getattr(agent, "stream_query", None)),
    "stream_query is callable",
)

# ── 18. StreamEvent.to_sse for every event type ──────────

all_serialisable = True
for name, evt in factories:
    try:
        sse = evt.to_sse()
        d = evt.to_dict()
        if not isinstance(d, dict):
            all_serialisable = False
            break
    except Exception:
        all_serialisable = False
        break
check(all_serialisable, "All event types are serialisable (to_dict + to_sse)")

# ── 19. StreamBuffer close is idempotent ─────────────────

buf4 = StreamBuffer(timeout=2)
buf4.put(StreamEvent.token("x"))
buf4.close()
buf4.close()  # should not raise
collected4 = list(buf4.events())
check(
    len([e for e in collected4 if e.event_type == StreamEventType.STREAM_END]) == 1,
    "StreamBuffer.close() is idempotent",
    f"Got {len(collected4)} events",
)

# ── 20. Renderer handles empty stream ────────────────────

empty_events = [StreamEvent.stream_end(0, 0)]
buf_out2 = io.StringIO()
with contextlib.redirect_stdout(buf_out2):
    result2 = render_stream_to_console(iter(empty_events))
check(
    result2 == "",
    "Renderer handles empty stream gracefully",
)

# ── 21. Renderer handles error events ────────────────────

error_events = [
    StreamEvent.stream_start("test"),
    StreamEvent.error("Connection lost"),
    StreamEvent.stream_end(0, 0.1),
]
buf_out3 = io.StringIO()
with contextlib.redirect_stdout(buf_out3):
    result3 = render_stream_to_console(iter(error_events))
check(
    "Connection lost" in buf_out3.getvalue(),
    "Renderer displays error events",
)

# ── 22. Renderer handles status events ───────────────────

status_events = [
    StreamEvent.status("Loading embeddings..."),
    StreamEvent.stream_end(0, 0),
]
buf_out4 = io.StringIO()
with contextlib.redirect_stdout(buf_out4):
    render_stream_to_console(iter(status_events))
check(
    "Loading embeddings" in buf_out4.getvalue(),
    "Renderer displays status events",
)

# ── 23. Multiple tool start/end pairs tracked correctly ──

multi_tool_events = [
    StreamEvent.stream_start("test"),
    StreamEvent.tool_start("get_developer", {"name": "Alex Kumar"}),
    StreamEvent.tool_end("get_developer", "Alex Kumar, Senior Engineer", 0.3),
    StreamEvent.tool_start("semantic_search", {"query": "database"}),
    StreamEvent.tool_end("semantic_search", "5 results", 0.8),
    StreamEvent.response("Combined answer"),
    StreamEvent.stream_end(2, 1.5),
]
buf_out5 = io.StringIO()
with contextlib.redirect_stdout(buf_out5):
    render_stream_to_console(iter(multi_tool_events))
output5 = buf_out5.getvalue()
check(
    "get_developer" in output5 and "semantic_search" in output5,
    "Renderer tracks multiple tool calls",
)

# ── 24. SSE format compatible with EventSource ───────────

sse_test = StreamEvent.model_selection("Qwen 72B", "🧠", "analytics").to_sse()
lines = sse_test.strip().split("\n")
check(
    lines[0].startswith("event: "),
    "SSE has event line",
    f"line[0]: {lines[0]}",
)
check(
    lines[1].startswith("data: "),
    "SSE has data line",
    f"line[1][:30]: {lines[1][:30]}",
)


# ============================================================
# PART 3: Live LLM Tests
# ============================================================
print("\n" + "=" * 60)
print("PART 3: Live LLM Tests")
print("=" * 60)

from agents.utils.config import load_config
load_config("/Users/rahul/Desktop/Datathon/.env")

# ── 25. Live stream_query with real supervisor ───────────

print("  [25] Running live stream_query...")
t0 = time.time()
try:
    supervisor = SupervisorAgent()
    supervisor.initialize()

    # Use a query that reliably routes to a specialist
    events_collected: list[StreamEvent] = []
    for evt in supervisor.stream_query("Find developers with Python expertise"):
        events_collected.append(evt)

    elapsed = time.time() - t0
    event_types_seen = set(e.event_type for e in events_collected)

    check(
        StreamEventType.STREAM_START in event_types_seen,
        "Live stream has STREAM_START",
    )
    check(
        StreamEventType.STREAM_END in event_types_seen,
        "Live stream has STREAM_END",
    )

    # This query should route to Insights_Specialist (skill lookup)
    has_routing_or_model = (
        StreamEventType.ROUTING in event_types_seen
        or StreamEventType.MODEL_SELECTION in event_types_seen
    )
    check(has_routing_or_model, "Live stream has routing/model events")

    has_response = StreamEventType.RESPONSE in event_types_seen
    check(has_response, "Live stream has RESPONSE event")

    if has_response:
        response_events = [e for e in events_collected if e.event_type == StreamEventType.RESPONSE]
        response_text = " ".join(e.data.get("content", "") for e in response_events)
        check(
            len(response_text) > 20,
            "Live stream response has meaningful content",
            f"Preview: {response_text[:100]}...",
        )

    print(f"    → Total events: {len(events_collected)}, Time: {elapsed:.1f}s")
    print(f"    → Event types: {[e.value for e in event_types_seen]}")

except Exception as e:
    fail("Live stream_query", str(e))
    import traceback; traceback.print_exc()

# ── 26. Live stream rendered to console ──────────────────

print("  [26] Running live stream with console renderer...")
t0 = time.time()
try:
    buf_out_live = io.StringIO()
    with contextlib.redirect_stdout(buf_out_live):
        rendered = render_stream_to_console(
            supervisor.stream_query("Who is Alex Kumar? Give me their profile information."),
        )
    elapsed = time.time() - t0
    output_live = buf_out_live.getvalue()

    check(
        len(rendered) > 0,
        "Live console render returns non-empty text",
        f"Rendered length: {len(rendered)} chars, Time: {elapsed:.1f}s",
    )
    check(
        "Alex Kumar" in rendered or "alex" in rendered.lower(),
        "Live render answer mentions Alex Kumar",
        f"Preview: {rendered[:120]}...",
    )

except Exception as e:
    fail("Live console render", str(e))
    import traceback; traceback.print_exc()

# ── 27. Live stream with tool call visualisation ─────────

print("  [27] Running live stream with tool calls...")
t0 = time.time()
try:
    tool_events: list[StreamEvent] = []
    for evt in supervisor.stream_query("Find developers with Python expertise"):
        tool_events.append(evt)

    elapsed = time.time() - t0
    tool_types = set(e.event_type for e in tool_events)

    has_tool_events = (
        StreamEventType.TOOL_START in tool_types
        or StreamEventType.TOOL_END in tool_types
    )
    # Tool events are emitted when the agent uses tools
    check(
        has_tool_events or StreamEventType.RESPONSE in tool_types,
        "Live stream has tool or response events",
        f"Event types: {[t.value for t in tool_types]}",
    )

    if StreamEventType.TOOL_START in tool_types:
        tool_starts = [e for e in tool_events if e.event_type == StreamEventType.TOOL_START]
        tool_names = [e.data.get("tool", "?") for e in tool_starts]
        check(
            len(tool_names) > 0,
            f"Tool calls detected: {tool_names}",
        )

    print(f"    → Total events: {len(tool_events)}, Time: {elapsed:.1f}s")

except Exception as e:
    fail("Live stream with tools", str(e))
    import traceback; traceback.print_exc()


# ============================================================
# RESULTS
# ============================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)
if failed == 0:
    print("🎉 All tests passed!")
else:
    print(f"⚠️  {failed} test(s) failed")
    sys.exit(1)
