#!/usr/bin/env python3
"""
Tests for Feature 1.3 — Natural Language to SQL/Cypher Pipeline
================================================================
Part 1: Unit tests (source identification, validation, extraction)
Part 2: Integration (graph compilation, tool wrappers)
Part 3: Live LLM (end-to-end query generation + execution)
"""

import sys, os, json, re, time

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
# Part 1: Unit Tests
# ============================================================================
print("\n" + "=" * 60)
print("PART 1: Unit Tests")
print("=" * 60)


def test_extract_code_block_sql():
    """Extract SQL from markdown code blocks."""
    from agents.pipelines.nl_query_pipeline import _extract_code_block
    text = "Here's the query:\n```sql\nSELECT * FROM employees;\n```"
    assert _extract_code_block(text) == "SELECT * FROM employees;"


def test_extract_code_block_plain():
    """Extract query from plain text without code block."""
    from agents.pipelines.nl_query_pipeline import _extract_code_block
    text = "SELECT count(*) FROM events"
    assert _extract_code_block(text) == "SELECT count(*) FROM events"


def test_extract_code_block_cypher():
    """Extract Cypher from code block."""
    from agents.pipelines.nl_query_pipeline import _extract_code_block
    text = "```cypher\nMATCH (d:Developer) RETURN d.name\n```"
    assert _extract_code_block(text) == "MATCH (d:Developer) RETURN d.name"


def test_parse_json_object():
    """Parse JSON from various LLM output formats."""
    from agents.pipelines.nl_query_pipeline import _parse_json_object
    # Direct JSON
    assert _parse_json_object('{"database": "postgres"}')["database"] == "postgres"
    # JSON in code block
    assert _parse_json_object('```json\n{"database": "clickhouse"}\n```')["database"] == "clickhouse"
    # JSON with surrounding text
    assert _parse_json_object('I think {"database": "neo4j"} is right')["database"] == "neo4j"


def test_validate_destructive_query():
    """Ensure destructive queries are rejected."""
    from agents.pipelines.nl_query_pipeline import validate_query_node
    state = {
        "question": "Delete all employees",
        "target_db": "postgres",
        "generated_query": "DELETE FROM employees WHERE active = false",
        "query_language": "sql",
        "validation_result": "",
        "retry_count": 0,
        "query_results": [],
        "execution_error": "",
        "summary": "",
        "status": "ok",
        "db_reason": "",
    }
    result = validate_query_node(state)
    assert "destructive" in result["validation_result"].lower() or "invalid" in result["validation_result"].lower()
    print(f"    → Rejected: {result['validation_result'][:80]}")


def test_validate_unknown_table():
    """Detect references to non-existent tables."""
    from agents.pipelines.nl_query_pipeline import validate_query_node
    state = {
        "question": "Get all users",
        "target_db": "postgres",
        "generated_query": "SELECT * FROM nonexistent_table",
        "query_language": "sql",
        "validation_result": "",
        "retry_count": 0,
        "query_results": [],
        "execution_error": "",
        "summary": "",
        "status": "ok",
        "db_reason": "",
    }
    result = validate_query_node(state)
    assert "unknown table" in result["validation_result"].lower() or "invalid" in result["validation_result"].lower()
    print(f"    → Rejected: {result['validation_result'][:80]}")


run_test("Extract SQL code block", test_extract_code_block_sql)
run_test("Extract plain query text", test_extract_code_block_plain)
run_test("Extract Cypher code block", test_extract_code_block_cypher)
run_test("Parse JSON from various formats", test_parse_json_object)
run_test("Reject destructive queries", test_validate_destructive_query)
run_test("Detect unknown tables", test_validate_unknown_table)


# ============================================================================
# Part 2: Integration Tests
# ============================================================================
print("\n" + "=" * 60)
print("PART 2: Integration Tests")
print("=" * 60)


def test_graph_compiles():
    """Ensure the NL→Query graph compiles."""
    from agents.pipelines.nl_query_pipeline import get_nl_query_graph
    g = get_nl_query_graph()
    assert g is not None
    nodes = list(g.get_graph().nodes)
    assert "identify_sources" in nodes, f"Missing identify_sources: {nodes}"
    assert "generate_query" in nodes
    assert "validate_query" in nodes
    assert "execute_query" in nodes
    assert "fix_query" in nodes
    assert "summarize" in nodes
    print(f"    → Nodes: {nodes}")


def test_tool_wrapper_exists():
    """Verify tool wrapper has correct schema."""
    from agents.tools.nl_query_tools import NL_QUERY_TOOLS
    assert len(NL_QUERY_TOOLS) == 1, f"Expected 1 tool, got {len(NL_QUERY_TOOLS)}"
    assert NL_QUERY_TOOLS[0].name == "natural_language_query"
    print(f"    → Tool: {NL_QUERY_TOOLS[0].name}")


def test_dora_agent_has_nl_query():
    """Verify NL query tool is in DORA agent."""
    from agents.specialists.dora_agent import DORA_TOOLS
    names = [t.name for t in DORA_TOOLS]
    assert "natural_language_query" in names, f"Missing in DORA agent: {names}"
    print(f"    → DORA tools ({len(names)}): {names}")


run_test("Graph compiles", test_graph_compiles)
run_test("Tool wrapper exists", test_tool_wrapper_exists)
run_test("DORA agent has NL query tool", test_dora_agent_has_nl_query)


# ============================================================================
# Part 3: Live LLM Tests
# ============================================================================
print("\n" + "=" * 60)
print("PART 3: Live LLM Tests")
print("=" * 60)


def test_postgres_query():
    """Generate and execute a PostgreSQL query."""
    from agents.pipelines.nl_query_pipeline import nl_query
    t0 = time.time()
    result = nl_query("How many employees are there in total?")
    elapsed = time.time() - t0

    assert result["status"] in ("ok", "max_retries"), f"Status: {result['status']}"
    assert result["target_db"] == "postgres", f"Expected postgres, got {result['target_db']}"
    assert result["summary"], "Empty summary"

    print(f"    → DB: {result['target_db']}, Query: {result['generated_query'][:80]}")
    print(f"    → Rows: {len(result.get('query_results', []))}, Retries: {result['retry_count']}")
    print(f"    → Summary: {result['summary'][:150]}...")
    print(f"    → Time: {elapsed:.1f}s")


def test_clickhouse_query():
    """Generate and execute a ClickHouse query."""
    from agents.pipelines.nl_query_pipeline import nl_query
    t0 = time.time()
    result = nl_query("How many events are there in the events table?")
    elapsed = time.time() - t0

    assert result["status"] in ("ok", "max_retries"), f"Status: {result['status']}"
    assert result["target_db"] == "clickhouse", f"Expected clickhouse, got {result['target_db']}"
    assert result["summary"], "Empty summary"

    print(f"    → DB: {result['target_db']}, Query: {result['generated_query'][:80]}")
    print(f"    → Rows: {len(result.get('query_results', []))}, Retries: {result['retry_count']}")
    print(f"    → Summary: {result['summary'][:150]}...")
    print(f"    → Time: {elapsed:.1f}s")


def test_tool_invoke():
    """Test the LangChain tool wrapper end-to-end."""
    from agents.tools.nl_query_tools import natural_language_query
    result = natural_language_query.invoke({"question": "List all team names"})
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 50, f"Result too short: {len(result)} chars"
    assert "Query Details" in result, "Missing metadata"
    print(f"    → Result: {len(result)} chars")
    print(f"    → Preview: {result[:200]}...")


run_test("PostgreSQL NL query", test_postgres_query)
run_test("ClickHouse NL query", test_clickhouse_query)
run_test("Tool wrapper invoke", test_tool_invoke)


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
