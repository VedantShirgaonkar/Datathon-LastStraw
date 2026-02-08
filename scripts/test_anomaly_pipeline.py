#!/usr/bin/env python3
"""
Test suite for Feature 2.1 — Anomaly Detection Pipeline
Tests data fetching, LLM anomaly detection, root cause investigation,
alert generation, and quality self-evaluation.
"""

import sys, os, json
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
            import traceback
            traceback.print_exc()
            failed += 1
    return decorator


# ============================================================================
# Part 1: Data fetching (ClickHouse)
# ============================================================================
print("\n" + "=" * 60)
print("Part 1: Data Fetching (ClickHouse)")
print("=" * 60)

from agents.pipelines.anomaly_pipeline import (
    fetch_current_node, fetch_baseline_node,
    detect_anomalies_node, investigate_node,
    generate_alert_node, evaluate_alert_node,
    get_anomaly_graph, run_anomaly_detection,
    AnomalyState,
)

def _make_state(**overrides) -> AnomalyState:
    base = {
        "project_id": None,
        "days_current": 7,
        "days_baseline": 30,
        "current_metrics": {},
        "baseline_metrics": {},
        "anomalies": [],
        "investigation": "",
        "alert_text": "",
        "quality_score": 0.0,
        "quality_feedback": "",
        "refine_count": 0,
        "status": "ok",
    }
    base.update(overrides)
    return base


@test("fetch_current_node returns DORA + events + dev activity")
def _():
    state = _make_state(days_current=30)
    result = fetch_current_node(state)
    metrics = result["current_metrics"]
    assert "dora" in metrics, f"Missing dora key: {list(metrics.keys())}"
    assert "events_by_project" in metrics
    assert "developer_activity" in metrics
    print(f"      DORA projects: {len(metrics['dora'])}, "
          f"Event projects: {len(metrics['events_by_project'])}, "
          f"Developers: {len(metrics['developer_activity'])}")


@test("fetch_baseline_node returns project + dev baselines")
def _():
    state = _make_state(days_baseline=60)
    result = fetch_baseline_node(state)
    baseline = result["baseline_metrics"]
    assert "project_baselines" in baseline
    assert "developer_baselines" in baseline
    print(f"      Project baselines: {len(baseline['project_baselines'])}, "
          f"Dev baselines: {len(baseline['developer_baselines'])}")


@test("fetch_current_node with project filter")
def _():
    state = _make_state(days_current=30, project_id="proj-api")
    result = fetch_current_node(state)
    metrics = result["current_metrics"]
    # Should have data (or empty but no error)
    assert "error" not in metrics, f"Got error: {metrics.get('error')}"
    print(f"      proj-api: DORA rows={len(metrics.get('dora', []))}")


# ============================================================================
# Part 2: Anomaly detection (LLM)
# ============================================================================
print("\n" + "=" * 60)
print("Part 2: Anomaly Detection (LLM)")
print("=" * 60)

@test("detect_anomalies_node with real data")
def _():
    # First fetch real data
    state = _make_state(days_current=7, days_baseline=30)
    state.update(fetch_current_node(state))
    state.update(fetch_baseline_node(state))
    
    result = detect_anomalies_node(state)
    anomalies = result.get("anomalies", [])
    status = result.get("status", "?")
    
    assert status in ("ok", "anomalies_found"), f"Unexpected status: {status}"
    print(f"      Status: {status}, Anomalies: {len(anomalies)}")
    for a in anomalies[:3]:
        print(f"        [{a.get('severity', '?')}] {a.get('description', '?')[:60]}")


@test("detect_anomalies_node returns valid structure")
def _():
    state = _make_state(days_current=7, days_baseline=30)
    state.update(fetch_current_node(state))
    state.update(fetch_baseline_node(state))
    result = detect_anomalies_node(state)
    
    for a in result.get("anomalies", []):
        assert "severity" in a, f"Missing severity in anomaly: {a}"
        assert a["severity"] in ("low", "medium", "high", "critical"), \
            f"Invalid severity: {a['severity']}"


# ============================================================================
# Part 3: Full pipeline end-to-end
# ============================================================================
print("\n" + "=" * 60)
print("Part 3: Full Pipeline (end-to-end)")
print("=" * 60)

@test("Graph compiles successfully")
def _():
    graph = get_anomaly_graph()
    assert graph is not None

@test("Full pipeline (all projects, 7d vs 30d)")
def _():
    result = run_anomaly_detection(
        project_id=None,
        days_current=7,
        days_baseline=30,
    )
    assert "anomalies" in result
    assert "alert_text" in result
    assert "status" in result
    assert result["status"] in ("ok", "anomalies_found", "error")
    
    print(f"      Status: {result['status']}")
    print(f"      Anomalies: {len(result['anomalies'])}")
    print(f"      Quality: {result.get('quality_score', 0):.0%}")
    print(f"      Refinements: {result.get('refine_count', 0)}")
    print(f"      Alert preview: {result['alert_text'][:150]}...")

    # Also verify the alert content is substantial when anomalies exist
    if result["anomalies"]:
        assert len(result["alert_text"]) > 50, \
            f"Alert too short: {result['alert_text'][:100]}"
        assert result.get("quality_score", 0) > 0, "Quality score is 0"
        print(f"      Alert length: {len(result['alert_text'])} chars ✓")
    else:
        print("      No anomalies — clean bill of health ✓")


# ============================================================================
# Part 4: Tool wrapper
# ============================================================================
print("\n" + "=" * 60)
print("Part 4: Tool Wrapper")
print("=" * 60)

from agents.tools.anomaly_tools import detect_anomalies, ANOMALY_TOOLS

@test("detect_anomalies tool is registered and callable")
def _():
    # Don't re-run the full pipeline (already tested above) — just verify the tool interface
    assert callable(detect_anomalies.invoke)
    assert detect_anomalies.name == "detect_anomalies"
    # Verify it has the correct parameters in its schema
    schema = detect_anomalies.args_schema.schema() if hasattr(detect_anomalies, 'args_schema') else {}
    print(f"      Tool name: {detect_anomalies.name}")
    print(f"      Schema properties: {list(schema.get('properties', {}).keys())}")

@test("ANOMALY_TOOLS export")
def _():
    assert len(ANOMALY_TOOLS) == 1
    assert ANOMALY_TOOLS[0].name == "detect_anomalies"

@test("DORA agent includes anomaly tool")
def _():
    from agents.specialists.dora_agent import DORA_TOOLS
    tool_names = [t.name for t in DORA_TOOLS]
    assert "detect_anomalies" in tool_names, f"Missing detect_anomalies in DORA tools: {tool_names}"
    print(f"      DORA tools: {tool_names}")


# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed}/{total} passed" + (f", {failed} FAILED" if failed else " ✅ All passed!"))
print("=" * 60)
sys.exit(1 if failed else 0)
