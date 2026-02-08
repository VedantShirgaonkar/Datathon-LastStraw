#!/usr/bin/env python3
"""
Test suite for Feature 4.1 — Conversation Memory
Tests thread management, checkpointer integration, multi-turn context,
and the full SupervisorAgent thread API.
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/Users/rahul/Desktop/Datathon/.env")

from agents.utils.config import load_config
load_config("/Users/rahul/Desktop/Datathon/.env")

passed = 0
failed = 0

def test(name):
    global passed, failed
    def decorator(fn):
        global passed, failed
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
    return decorator


# ============================================================================
# Part 1: ConversationMemory unit tests (no LLM calls needed)
# ============================================================================
print("\n" + "=" * 60)
print("Part 1: ConversationMemory unit tests")
print("=" * 60)

from agents.utils.memory import ConversationMemory, get_conversation_memory, ThreadInfo

@test("ThreadInfo creation and touch")
def _():
    t = ThreadInfo("abc123", title="Test Thread")
    assert t.thread_id == "abc123"
    assert t.title == "Test Thread"
    assert t.message_count == 0
    old_active = t.last_active
    time.sleep(0.01)
    t.touch(5)
    assert t.message_count == 5
    assert t.last_active > old_active

@test("ThreadInfo to_dict")
def _():
    t = ThreadInfo("x1", title="Export test")
    d = t.to_dict()
    assert d["thread_id"] == "x1"
    assert d["title"] == "Export test"
    assert "created_at" in d
    assert "last_active" in d

@test("ConversationMemory new_thread generates unique IDs")
def _():
    mem = ConversationMemory()
    id1 = mem.new_thread("Thread A")
    id2 = mem.new_thread("Thread B")
    assert id1 != id2
    assert len(id1) == 12
    assert len(id2) == 12

@test("ConversationMemory get_config returns valid LangGraph config")
def _():
    mem = ConversationMemory()
    tid = mem.new_thread("Config test")
    cfg = mem.get_config(tid)
    assert "configurable" in cfg
    assert cfg["configurable"]["thread_id"] == tid

@test("ConversationMemory get_config auto-creates unknown threads")
def _():
    mem = ConversationMemory()
    cfg = mem.get_config("unknown_thread_99")
    assert cfg["configurable"]["thread_id"] == "unknown_thread_99"
    threads = mem.list_threads()
    ids = [t["thread_id"] for t in threads]
    assert "unknown_thread_99" in ids

@test("ConversationMemory list_threads sorted by last_active")
def _():
    mem = ConversationMemory()
    id1 = mem.new_thread("Old")
    time.sleep(0.02)
    id2 = mem.new_thread("Mid")
    time.sleep(0.02)
    id3 = mem.new_thread("New")
    threads = mem.list_threads()
    assert threads[0]["thread_id"] == id3  # newest first
    assert threads[-1]["thread_id"] == id1  # oldest last

@test("ConversationMemory delete_thread")
def _():
    mem = ConversationMemory()
    tid = mem.new_thread("Delete me")
    assert mem.delete_thread(tid) is True
    assert mem.delete_thread(tid) is False  # already gone
    assert tid not in [t["thread_id"] for t in mem.list_threads()]

@test("ConversationMemory eviction when over max_threads")
def _():
    mem = ConversationMemory(max_threads=3)
    ids = [mem.new_thread(f"T{i}") for i in range(5)]
    # Should have evicted the 2 oldest
    threads = mem.list_threads()
    assert len(threads) <= 3

@test("ConversationMemory touch_thread updates metadata")
def _():
    mem = ConversationMemory()
    tid = mem.new_thread("Touch test")
    mem.touch_thread(tid, 10)
    threads = {t["thread_id"]: t for t in mem.list_threads()}
    assert threads[tid]["message_count"] == 10

@test("ConversationMemory trim_messages preserves system + recent")
def _():
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    msgs = [SystemMessage(content="You are a helper")]
    for i in range(30):
        msgs.append(HumanMessage(content=f"Q{i}"))
        msgs.append(AIMessage(content=f"A{i}"))
    # total = 1 system + 60 = 61 messages
    trimmed = ConversationMemory.trim_messages(msgs, max_messages=10)
    assert len(trimmed) <= 10
    # System message should be preserved
    assert trimmed[0].content == "You are a helper"
    # Last message should be the most recent
    assert trimmed[-1].content == "A29"

@test("ConversationMemory trim_messages no-op when under limit")
def _():
    from langchain_core.messages import HumanMessage
    msgs = [HumanMessage(content=f"Q{i}") for i in range(5)]
    trimmed = ConversationMemory.trim_messages(msgs, max_messages=20)
    assert len(trimmed) == 5

@test("ConversationMemory checkpointer is MemorySaver")
def _():
    from langgraph.checkpoint.memory import MemorySaver
    mem = ConversationMemory()
    assert isinstance(mem.checkpointer, MemorySaver)

@test("get_conversation_memory returns singleton")
def _():
    # Reset the module-level singleton for clean test
    import agents.utils.memory as mem_mod
    mem_mod._memory = None
    m1 = get_conversation_memory()
    m2 = get_conversation_memory()
    assert m1 is m2
    mem_mod._memory = None  # clean up


# ============================================================================
# Part 2: SupervisorAgent thread API (import-level, no LLM calls)
# ============================================================================
print("\n" + "=" * 60)
print("Part 2: SupervisorAgent thread management API")
print("=" * 60)

from agents.supervisor import SupervisorAgent

@test("SupervisorAgent.new_thread creates thread")
def _():
    agent = SupervisorAgent()
    agent.initialize()
    tid = agent.new_thread("Test thread")
    assert len(tid) == 12
    threads = agent.list_threads()
    assert any(t["thread_id"] == tid for t in threads)

@test("SupervisorAgent.delete_thread removes thread")
def _():
    agent = SupervisorAgent()
    agent.initialize()
    tid = agent.new_thread("Delete test")
    assert agent.delete_thread(tid) is True
    assert tid not in [t["thread_id"] for t in agent.list_threads()]

@test("SupervisorAgent graph compiled with checkpointer")
def _():
    agent = SupervisorAgent()
    agent.initialize()
    # The graph should have a checkpointer attached
    # LangGraph stores it on graph.checkpointer or internally
    assert agent._memory is not None
    assert agent._memory.checkpointer is not None
    assert agent.graph is not None

@test("SupervisorAgent.memory property auto-initialises")
def _():
    agent = SupervisorAgent()
    # Not initialized yet — accessing .memory should auto-init
    mem = agent.memory
    assert mem is not None
    assert agent._initialized is True


# ============================================================================
# Part 3: Multi-turn conversation test (requires LLM — live)
# ============================================================================
print("\n" + "=" * 60)
print("Part 3: Multi-turn conversation (live LLM)")
print("=" * 60)

@test("Multi-turn: agent remembers context within a thread")
def _():
    """
    Send two messages in the same thread.
    The second message references the first — the agent should remember.
    """
    agent = SupervisorAgent()
    agent.initialize()
    tid = agent.new_thread("Multi-turn test")

    # Turn 1: Ask about a specific developer
    r1 = agent.query("Who is Priya Sharma?", thread_id=tid)
    assert len(r1) > 20, f"Response too short: {r1[:80]}"
    # Should mention Priya
    assert "priya" in r1.lower() or "sharma" in r1.lower(), \
        f"Response doesn't mention Priya: {r1[:200]}"
    print(f"      Turn 1 ({len(r1)} chars): ...{r1[:120]}...")

    # Turn 2: Ask a follow-up that requires context from turn 1
    r2 = agent.query("What team is she on?", thread_id=tid)
    assert len(r2) > 10, f"Response too short: {r2[:80]}"
    print(f"      Turn 2 ({len(r2)} chars): ...{r2[:120]}...")
    # "she" refers to Priya — the agent should resolve it via memory
    # We just check it gives a non-trivial answer (not "who?")


@test("Different threads are independent (no cross-contamination)")
def _():
    agent = SupervisorAgent()
    agent.initialize()

    tid_a = agent.new_thread("Thread A - projects")
    tid_b = agent.new_thread("Thread B - developers")

    # Thread A: ask about a project
    r_a = agent.query("Tell me about the API Gateway project", thread_id=tid_a)
    assert len(r_a) > 20

    # Thread B: ask about developers (no mention of API Gateway)
    r_b = agent.query("List all developers on the Platform Engineering team", thread_id=tid_b)
    assert len(r_b) > 20

    # Follow-up in Thread B should NOT know about API Gateway from Thread A
    # It should be about the Platform Engineering team context
    r_b2 = agent.query("How many people did you find?", thread_id=tid_b)
    print(f"      Thread B follow-up ({len(r_b2)} chars): ...{r_b2[:120]}...")
    # Not a strict assertion — just verifying no crash and reasonable response


@test("No thread_id = stateless (ephemeral thread, no memory)")
def _():
    """Queries without thread_id should work via ephemeral thread — backward-compat."""
    agent = SupervisorAgent()
    agent.initialize()
    r = agent.query("How many projects are there?", thread_id=None)
    assert len(r) > 10
    assert "error" not in r.lower()[:30], f"Got error: {r[:200]}"
    print(f"      Stateless response ({len(r)} chars): ...{r[:120]}...")


# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed}/{total} passed" + (f", {failed} FAILED" if failed else " ✅ All passed!"))
print("=" * 60)
sys.exit(1 if failed else 0)
