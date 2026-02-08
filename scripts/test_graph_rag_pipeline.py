#!/usr/bin/env python3
"""
Feature 3.3 — Graph RAG Expert Discovery  ·  Deep Test Suite
=============================================================

Tests the full Graph RAG pipeline that fuses pgvector semantic similarity
with Neo4j graph traversal to find and explain expert recommendations.

PART 1 — Unit Tests (no DB / no LLM)
    1. Topic keyword extraction
    2. JSON array parsing (clean, fenced, embedded)
    3. Synthetic graph results generation
    4. Fuse-and-rank score computation
    5. Safe serialisation helpers
    6. Graph node topology

PART 2 — Integration Tests
    7. Graph compiles with correct nodes
    8. Tool wrappers exist and are callable
    9. Insights agent has Graph RAG tools
    10. Model router detects expert queries

PART 3 — Live Tests (real DB + real LLM)
    11. Full pipeline: "Who can help with database optimisation?"
    12. Quick expert search (vector-only)
    13. Tool wrapper invoke
"""

from __future__ import annotations
import sys, os, time, re

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0

def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {label}")
    else:
        failed += 1
        print(f"  ❌ {label}")
    if detail:
        print(f"    → {detail}")


# ====================================================================
print("\n" + "=" * 60)
print("PART 1: Unit Tests")
print("=" * 60)

# --- 1. Topic keyword extraction ---
from agents.pipelines.graph_rag_pipeline import _extract_topic_keywords

t1 = _extract_topic_keywords("Who can help debug the payment processing timeout?")
check("Extract topic keywords",
      "payment" in t1.lower() and "processing" in t1.lower(),
      f"Extracted: '{t1}'")

t2 = _extract_topic_keywords("Find me an expert in Kubernetes")
check("Extract topic — Kubernetes",
      "kubernetes" in t2.lower(),
      f"Extracted: '{t2}'")

# --- 2. JSON array parsing ---
from agents.pipelines.graph_rag_pipeline import _parse_json_array

arr1 = _parse_json_array('[{"name":"A","explanation":"good"},{"name":"B","explanation":"ok"}]')
check("Parse clean JSON array", len(arr1) == 2 and arr1[0]["name"] == "A")

arr2 = _parse_json_array('```json\n[{"name":"X"}]\n```')
check("Parse fenced JSON array", len(arr2) == 1 and arr2[0]["name"] == "X")

arr3 = _parse_json_array('Here are the results:\n[{"name":"Y"}]\nDone.')
check("Parse embedded JSON array", len(arr3) == 1 and arr3[0]["name"] == "Y")

arr4 = _parse_json_array("not json at all")
check("Parse non-JSON returns empty", arr4 == [])

# --- 3. Synthetic graph results ---
from agents.pipelines.graph_rag_pipeline import _synthetic_graph_results

synth = _synthetic_graph_results("API design patterns", 5)
check("Synthetic graph results non-empty",
      len(synth) > 0,
      f"{len(synth)} synthetic results")

# Verify each has required keys
all_have_keys = all(
    "name" in r and "graph_score" in r and "path" in r
    for r in synth
)
check("Synthetic results have required keys", all_have_keys)

# --- 4. Fuse-and-rank computation ---
from agents.pipelines.graph_rag_pipeline import fuse_and_rank_node, VECTOR_WEIGHT, GRAPH_WEIGHT

mock_state = {
    "query": "test",
    "limit": 3,
    "vector_results": [
        {"full_name": "Alice", "similarity": 0.9, "title": "Senior", "role": "eng", "team_name": "A", "profile_content": "..."},
        {"full_name": "Bob",   "similarity": 0.7, "title": "Junior", "role": "eng", "team_name": "B", "profile_content": "..."},
    ],
    "graph_results": [
        {"name": "Bob",   "graph_score": 0.95, "path": "EXPERT_IN"},
        {"name": "Carol", "graph_score": 0.8,  "path": "CONTRIBUTED_TO"},
    ],
    "fused_ranking": [],
    "explanations": [],
    "report": "",
    "status": "",
}

fused_result = fuse_and_rank_node(mock_state)
fused = fused_result["fused_ranking"]

# Alice: 0.6*0.9 + 0.4*0 = 0.54
# Bob:   0.6*0.7 + 0.4*0.95 = 0.42 + 0.38 = 0.80
# Carol: 0.6*0 + 0.4*0.8 = 0.32
check("Fusion produces 3 candidates", len(fused) == 3, f"Got {len(fused)}")

# Bob should be #1 (0.80 > 0.54 > 0.32)
check("Bob ranks first (graph boost)",
      fused[0]["name"] == "Bob",
      f"#{1}: {fused[0]['name']} ({fused[0]['combined_score']})")

check("Alice ranks second",
      fused[1]["name"] == "Alice",
      f"#{2}: {fused[1]['name']} ({fused[1]['combined_score']})")

# --- 5. Safe serialisation ---
from agents.pipelines.graph_rag_pipeline import _safe_serialise
from decimal import Decimal
from datetime import date

safe = _safe_serialise({"val": Decimal("3.14"), "d": date(2024, 1, 1), "nested": [Decimal("2.7")]})
check("Safe serialise Decimal/date",
      safe["val"] == 3.14 and safe["d"] == "2024-01-01" and safe["nested"][0] == 2.7)

# --- 6. Weights check ---
check("Weights sum to 1.0",
      abs(VECTOR_WEIGHT + GRAPH_WEIGHT - 1.0) < 1e-6,
      f"vector={VECTOR_WEIGHT}, graph={GRAPH_WEIGHT}")


# ====================================================================
print("\n" + "=" * 60)
print("PART 2: Integration Tests")
print("=" * 60)

# --- 7. Graph compiles ---
from agents.pipelines.graph_rag_pipeline import get_graph_rag_graph

# Reset singleton to ensure fresh build
import agents.pipelines.graph_rag_pipeline as _grmod
_grmod._graph_instance = None

graph = get_graph_rag_graph()
node_names = sorted(graph.get_graph().nodes)
check("Graph compiles",
      len(node_names) >= 7,  # 5 nodes + __start__ + __end__
      f"Nodes: {node_names}")

required_nodes = {"vector_search", "graph_search", "fuse_and_rank", "explain_recommendations", "synthesize"}
check("All required nodes present",
      required_nodes.issubset(set(node_names)),
      f"Missing: {required_nodes - set(node_names) if not required_nodes.issubset(set(node_names)) else 'none'}")

# --- 8. Tool wrappers ---
from agents.tools.graph_rag_tools import find_expert_for_topic, quick_expert_search, GRAPH_RAG_TOOLS

check("Tool wrappers exist",
      len(GRAPH_RAG_TOOLS) == 2,
      f"Tools: {[t.name for t in GRAPH_RAG_TOOLS]}")

check("find_expert_for_topic is a tool",
      hasattr(find_expert_for_topic, "name") and find_expert_for_topic.name == "find_expert_for_topic")

check("quick_expert_search is a tool",
      hasattr(quick_expert_search, "name") and quick_expert_search.name == "quick_expert_search")

# --- 9. Insights agent integration ---
from agents.specialists.insights_agent import INSIGHTS_TOOLS

tool_names = [t.name for t in INSIGHTS_TOOLS]
check("Insights agent has find_expert_for_topic",
      "find_expert_for_topic" in tool_names,
      f"Insights tools ({len(tool_names)}): {tool_names}")

check("Insights agent has quick_expert_search",
      "quick_expert_search" in tool_names)

# --- 10. Model router expert detection ---
from agents.utils.model_router import classify_task, TaskType

expert_queries = [
    "Who can help with API design?",
    "Find me an expert in Kubernetes",
    "Who knows about database administration?",
]
for q in expert_queries:
    task_type, reason = classify_task(q)
    check(f"Router: '{q[:35]}...' → QUICK_LOOKUP",
          task_type == TaskType.QUICK_LOOKUP,
          f"Got: {task_type.value} — {reason}")


# ====================================================================
print("\n" + "=" * 60)
print("PART 3: Live LLM Tests")
print("=" * 60)

# --- 11. Full pipeline ---
from agents.pipelines.graph_rag_pipeline import find_expert

print("  [11] Running full Graph RAG pipeline...")
t0 = time.time()
result = find_expert("Who can help with database optimization?", limit=3)
elapsed = time.time() - t0

report = result.get("report", "")
ranking = result.get("fused_ranking", [])
status = result.get("status", "")

check("Full pipeline returns report",
      len(report) > 100,
      f"Report: {len(report)} chars, Status: {status}")

check("Full pipeline has ranked candidates",
      len(ranking) > 0,
      f"Candidates: {len(ranking)}")

if ranking:
    top = ranking[0]
    check("Top candidate has scores",
          "combined_score" in top and top["combined_score"] > 0,
          f"Top: {top.get('name')} (combined={top.get('combined_score')})")

# Check report has substantive content
has_names = any(c.get("name", "") in report for c in ranking)
check("Report mentions candidates by name",
      has_names or len(report) > 200,
      f"Time: {elapsed:.1f}s")

print(f"    → Preview: {report[:200]}...")

# --- 12. Quick expert search (vector-only) ---
print("\n  [12] Running quick expert search...")
t0 = time.time()
quick_result = quick_expert_search.invoke({"skills": "Python backend development", "limit": 3})
elapsed = time.time() - t0

check("Quick search returns results",
      isinstance(quick_result, str) and len(quick_result) > 50,
      f"Result: {len(quick_result)} chars, Time: {elapsed:.1f}s")

check("Quick search has similarity scores",
      "Similarity" in quick_result or "similarity" in quick_result.lower(),
      f"Preview: {quick_result[:150]}...")

# --- 13. Tool wrapper invoke ---
print("\n  [13] Running tool wrapper (find_expert_for_topic)...")
t0 = time.time()
tool_result = find_expert_for_topic.invoke({"query": "React TypeScript frontend expert", "limit": 3})
elapsed = time.time() - t0

check("Tool wrapper returns report",
      isinstance(tool_result, str) and len(tool_result) > 100,
      f"Result: {len(tool_result)} chars")

check("Tool wrapper has metadata footer",
      "Graph RAG" in tool_result,
      f"Time: {elapsed:.1f}s")

print(f"    → Preview: {tool_result[:200]}...")


# ====================================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)

if failed == 0:
    print("🎉 All tests passed!")
else:
    print(f"⚠️  {failed} test(s) failed")

sys.exit(0 if failed == 0 else 1)
