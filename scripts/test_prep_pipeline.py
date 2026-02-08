#!/usr/bin/env python3
"""
Tests for Feature 2.3 — Developer 1:1 Prep Agent
=================================================
Part 1: Unit tests (pipeline nodes, data gathering)
Part 2: Integration (graph compilation, tool wrappers)
Part 3: Live LLM (end-to-end briefing generation)
Part 4: Routing (supervisor routes 1:1 queries correctly)
"""

import sys, os, json, asyncio, re, time

# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

passed = 0
failed = 0
total = 0


def run_test(name, fn):
    global passed, failed, total
    total += 1
    try:
        fn()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        print(f"  ❌ {name}: {e}")


# ============================================================================
# Part 1: Unit Tests — Pipeline Nodes
# ============================================================================
print("\n" + "=" * 60)
print("PART 1: Pipeline Node Unit Tests")
print("=" * 60)


def test_resolve_known_developer():
    """Resolve a developer that exists in PostgreSQL."""
    from agents.pipelines.prep_pipeline import resolve_developer_node
    state = {
        "developer_name": "Alex Kumar",
        "manager_context": "",
        "developer_info": {},
        "project_assignments": [],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }
    result = resolve_developer_node(state)
    assert result["status"] == "ok", f"Expected 'ok', got '{result['status']}'"
    assert result["developer_info"], "Expected non-empty developer_info"
    dev = result["developer_info"]
    assert "full_name" in dev, f"Missing 'full_name', keys: {list(dev.keys())}"
    print(f"    → Resolved: {dev.get('full_name')} ({dev.get('title', 'N/A')})")
    print(f"    → {len(result.get('project_assignments', []))} assignments")


def test_resolve_unknown_developer():
    """Handle a developer that doesn't exist."""
    from agents.pipelines.prep_pipeline import resolve_developer_node
    state = {
        "developer_name": "NonExistentPerson12345",
        "manager_context": "",
        "developer_info": {},
        "project_assignments": [],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }
    result = resolve_developer_node(state)
    assert result["status"] == "developer_not_found", f"Expected 'developer_not_found', got '{result['status']}'"


def test_gather_activity():
    """Gather ClickHouse activity for a developer."""
    from agents.pipelines.prep_pipeline import gather_activity_node
    # First resolve a dev
    from agents.pipelines.prep_pipeline import resolve_developer_node
    state = {
        "developer_name": "Alex Kumar",
        "manager_context": "",
        "developer_info": {},
        "project_assignments": [],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }
    resolved = resolve_developer_node(state)
    state.update(resolved)
    result = gather_activity_node(state)
    assert "recent_activity" in result, "Missing recent_activity"
    activity = result["recent_activity"]
    assert isinstance(activity, dict), f"Expected dict, got {type(activity)}"
    # Activity may or may not have data (depends on ClickHouse events)
    print(f"    → Activity sections: {list(activity.keys())}")


def test_gather_workload():
    """Compute workload from assignments."""
    from agents.pipelines.prep_pipeline import gather_workload_node
    state = {
        "developer_name": "Vedant",
        "developer_info": {"id": 1, "full_name": "Vedant", "hourly_rate": 50},
        "project_assignments": [
            {"project_name": "Project A", "allocated_percent": 60, "status": "active"},
            {"project_name": "Project B", "allocated_percent": 40, "status": "active"},
        ],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }
    result = gather_workload_node(state)
    assert "workload_info" in result, "Missing workload_info"
    wl = result["workload_info"]
    assert wl.get("total_allocation_pct") == 100, f"Expected 100%, got {wl.get('total_allocation_pct')}"
    assert wl.get("num_active_projects") == 2
    print(f"    → Allocation: {wl['total_allocation_pct']}%, "
          f"Over: {wl['overallocated']}, Under: {wl['underallocated']}")


def test_gather_collaboration():
    """Gather collaboration patterns."""
    from agents.pipelines.prep_pipeline import gather_collaboration_node
    from agents.pipelines.prep_pipeline import resolve_developer_node
    state = {
        "developer_name": "Alex Kumar",
        "manager_context": "",
        "developer_info": {},
        "project_assignments": [],
        "recent_activity": {},
        "workload_info": {},
        "collaboration_patterns": [],
        "skill_context": [],
        "briefing": "",
        "talking_points": [],
        "status": "ok",
    }
    resolved = resolve_developer_node(state)
    state.update(resolved)
    result = gather_collaboration_node(state)
    assert "collaboration_patterns" in result
    assert "skill_context" in result
    print(f"    → {len(result['collaboration_patterns'])} collaborators, "
          f"{len(result['skill_context'])} skill embeddings")


run_test("Resolve known developer", test_resolve_known_developer)
run_test("Resolve unknown developer", test_resolve_unknown_developer)
run_test("Gather activity from ClickHouse", test_gather_activity)
run_test("Compute workload from assignments", test_gather_workload)
run_test("Gather collaboration patterns", test_gather_collaboration)


# ============================================================================
# Part 2: Integration — Graph & Tool Wrappers
# ============================================================================
print("\n" + "=" * 60)
print("PART 2: Integration Tests")
print("=" * 60)


def test_graph_compiles():
    """Ensure the prep graph compiles without error."""
    from agents.pipelines.prep_pipeline import get_prep_graph
    g = get_prep_graph()
    assert g is not None, "Graph is None"
    # Check nodes are present
    nodes = list(g.get_graph().nodes)
    assert "resolve" in nodes, f"Missing 'resolve' node. Nodes: {nodes}"
    assert "synthesize" in nodes, f"Missing 'synthesize' node. Nodes: {nodes}"
    print(f"    → Graph nodes: {nodes}")


def test_tool_wrapper_exists():
    """Verify the tool wrapper has correct schema."""
    from agents.tools.prep_tools import PREP_TOOLS
    assert len(PREP_TOOLS) == 2, f"Expected 2 tools, got {len(PREP_TOOLS)}"
    names = [t.name for t in PREP_TOOLS]
    assert "prepare_one_on_one" in names, f"Missing 'prepare_one_on_one': {names}"
    assert "suggest_talking_points" in names, f"Missing 'suggest_talking_points': {names}"
    print(f"    → Tools: {names}")


def test_resource_agent_has_prep_tools():
    """Verify prep tools are integrated into Resource Agent."""
    from agents.specialists.resource_agent import RESOURCE_TOOLS
    names = [t.name for t in RESOURCE_TOOLS]
    assert "prepare_one_on_one" in names, f"Missing in resource agent: {names}"
    assert "suggest_talking_points" in names, f"Missing in resource agent: {names}"
    print(f"    → Resource Agent tools ({len(names)}): {names}")


def test_model_router_1on1_detection():
    """Verify the model router classifies 1:1 queries as PLANNING."""
    from agents.utils.model_router import classify_task, TaskType
    queries = [
        "prepare for my 1:1 with Vedant",
        "one-on-one meeting prep for Sarah",
        "generate talking points for my meeting",
        "1:1 briefing for the team lead",
        "prep my one on one with John",
    ]
    for q in queries:
        task_type, reason = classify_task(q)
        assert task_type == TaskType.PLANNING, f"Query '{q}' classified as {task_type}, expected PLANNING"
    print(f"    → All {len(queries)} 1:1 queries classified as PLANNING ✓")


run_test("Graph compiles", test_graph_compiles)
run_test("Tool wrappers exist", test_tool_wrapper_exists)
run_test("Resource agent has prep tools", test_resource_agent_has_prep_tools)
run_test("Model router detects 1:1 queries", test_model_router_1on1_detection)


# ============================================================================
# Part 3: Live LLM — Full Pipeline
# ============================================================================
print("\n" + "=" * 60)
print("PART 3: Live LLM Tests (requires API keys)")
print("=" * 60)


def test_full_pipeline_known_developer():
    """Run the complete pipeline for a known developer."""
    from agents.pipelines.prep_pipeline import prepare_one_on_one
    t0 = time.time()
    result = prepare_one_on_one(developer_name="Alex Kumar")
    elapsed = time.time() - t0

    assert result["status"] == "ok", f"Expected 'ok', got '{result['status']}'"
    assert result["briefing"], "Empty briefing"
    assert len(result["briefing"]) > 200, f"Briefing too short: {len(result['briefing'])} chars"

    # Check the briefing has structure
    briefing = result["briefing"]
    has_sections = any(marker in briefing for marker in
                       ["📋", "🎯", "⚠️", "💬", "🌱", "📊",
                        "Profile", "Accomplishment", "Concern",
                        "Talking", "Growth", "Metric"])
    assert has_sections, "Briefing lacks expected section markers"

    tp = result.get("talking_points", [])

    print(f"    → Briefing: {len(briefing)} chars, {len(tp)} talking points")
    print(f"    → Dev: {result.get('developer_info', {}).get('full_name', '?')}")
    print(f"    → Time: {elapsed:.1f}s")
    # Print a snippet
    print(f"    → Preview: {briefing[:200]}...")


def test_full_pipeline_unknown_developer():
    """Pipeline gracefully handles unknown developer."""
    from agents.pipelines.prep_pipeline import prepare_one_on_one
    result = prepare_one_on_one(developer_name="ZzzNonexistent999")
    assert result["status"] == "developer_not_found", f"Expected 'developer_not_found', got '{result['status']}'"
    assert "not found" in result["briefing"].lower() or "❌" in result["briefing"]
    print(f"    → Correctly returned: {result['briefing'][:80]}")


def test_tool_wrapper_invoke():
    """Test the LangChain tool wrapper end-to-end."""
    from agents.tools.prep_tools import prepare_one_on_one
    result = prepare_one_on_one.invoke({"developer_name": "Alex Kumar"})
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 100, f"Result too short: {len(result)} chars"
    assert "Briefing Metadata" in result, "Missing metadata footer"
    print(f"    → Tool result: {len(result)} chars")
    print(f"    → Preview: {result[:150]}...")


run_test("Full pipeline — known developer", test_full_pipeline_known_developer)
run_test("Full pipeline — unknown developer", test_full_pipeline_unknown_developer)
run_test("Tool wrapper invoke", test_tool_wrapper_invoke)


# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    print("⚠️  Some tests failed!")
    sys.exit(1)
else:
    print("🎉 All tests passed!")
    sys.exit(0)
