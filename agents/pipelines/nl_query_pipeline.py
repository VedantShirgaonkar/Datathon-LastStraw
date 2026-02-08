"""
Natural Language to SQL/Cypher Pipeline (Feature 1.3)
=====================================================
LangGraph sub-graph that translates natural language questions into
executable database queries, validates them, self-corrects on failure,
and synthesizes natural language summaries.

Pipeline:
    identify_sources → generate_query → validate_query
        ├── valid → execute_query → summarize → END
        └── invalid → fix_query → validate_query (max 3 retries)
"""

from __future__ import annotations

import json
import re
from typing import TypedDict, Optional, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from agents.utils.logger import get_logger, log_llm_call
from agents.utils.config import get_config
from agents.utils.db_clients import get_postgres_client, get_clickhouse_client

logger = get_logger(__name__, "NL_QUERY")


# ============================================================================
# Database Schema Context (embedded for prompt injection)
# ============================================================================

POSTGRES_SCHEMA = """
PostgreSQL Tables:
1. employees (id UUID PK, email TEXT, full_name TEXT, team_id UUID FK→teams.id,
   role TEXT, hourly_rate NUMERIC, title TEXT, manager_id UUID FK→employees.id,
   location TEXT, timezone TEXT, employment_type TEXT, level TEXT,
   start_date DATE, active BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP)
2. teams (id UUID PK, name TEXT, department TEXT, manager_id UUID FK→employees.id,
   created_at TIMESTAMP)
3. projects (id UUID PK, name TEXT, description TEXT, github_repo TEXT,
   jira_project_key TEXT, notion_database_id TEXT, status TEXT, priority TEXT,
   target_date DATE, created_at TIMESTAMP)
   NOTE: projects has NO team_id column.
4. project_assignments (id UUID PK, employee_id UUID FK→employees.id,
   project_id UUID FK→projects.id, role TEXT, allocated_percent NUMERIC,
   assigned_at TIMESTAMP, start_date DATE, end_date DATE)
5. embeddings (id UUID PK, embedding_type TEXT, source_id TEXT,
   source_table TEXT, embedding VECTOR(1024), title TEXT, content TEXT,
   metadata JSONB, created_at TIMESTAMP, updated_at TIMESTAMP)

Key Relationships:
- employees.team_id → teams.id
- employees.manager_id → employees.id (self-referential)
- project_assignments.employee_id → employees.id
- project_assignments.project_id → projects.id
- teams.manager_id → employees.id
"""

CLICKHOUSE_SCHEMA = """
ClickHouse Tables:
1. events (event_id UUID, timestamp DateTime, source String,
   event_type String, project_id String, actor_id String,
   entity_id String, entity_type String, metadata String)
   event_type values: 'commit', 'pr_merged', 'pr_reviewed', 'pr_opened',
   'deploy', 'issue_created', 'issue_closed'
   actor_id is the developer email.
2. dora_daily_metrics (date Date, project_id String,
   deployments UInt32, avg_lead_time_hours Float64,
   prs_merged UInt32, commits UInt32,
   story_points_completed Float64, failed_deployments UInt32)
"""

NEO4J_SCHEMA = """
Neo4j Graph Schema:
Nodes: (:Developer {name, email, team}), (:Project {name, status}),
       (:Team {name, department})
Relationships: (Developer)-[:WORKS_ON]->(Project),
               (Developer)-[:COLLABORATES_WITH]->(Developer),
               (Developer)-[:MEMBER_OF]->(Team)
Note: Neo4j may have limited data — prefer PostgreSQL/ClickHouse.
"""


# ============================================================================
# State
# ============================================================================

class NLQueryState(TypedDict):
    """State flowing through the NL→Query pipeline."""
    # Input
    question: str                  # Natural language question
    # Resolved
    target_db: str                 # "postgres" | "clickhouse" | "neo4j"
    db_reason: str                 # Why this database was chosen
    generated_query: str           # SQL or Cypher query
    query_language: str            # "sql" | "cypher"
    validation_result: str         # "valid" | error description
    query_results: list            # Raw query results
    execution_error: str           # Error from execution, if any
    summary: str                   # Natural language summary of results
    retry_count: int               # Number of fix attempts
    status: str                    # "ok" | "error" | "max_retries"


MAX_RETRIES = 3


# ============================================================================
# Helpers
# ============================================================================

def _get_llm(model_key: str = "primary", temperature: float = 0.0):
    \"\"\"Create an LLM instance using the centralized get_llm helper.\"\"\"
    from agents.utils.model_router import get_llm
    return get_llm(temperature=temperature)


def _extract_code_block(text: str) -> str:
    """Extract SQL/Cypher from markdown code blocks or raw text."""
    # Try ```sql ... ``` or ```cypher ... ``` or ``` ... ```
    m = re.search(r"```(?:sql|cypher|)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try single-line code
    m = re.search(r"`([^`]+)`", text)
    if m and len(m.group(1)) > 10:
        return m.group(1).strip()
    # Return the text after common prefixes
    for prefix in ["SQL:", "Query:", "Cypher:"]:
        if prefix in text:
            return text.split(prefix, 1)[1].strip()
    return text.strip()


def _safe_serialise(rows: list, max_rows: int = 50) -> list:
    """Safely serialise query results for LLM consumption."""
    import math
    from datetime import datetime, date as date_type
    out = []
    for row in rows[:max_rows]:
        clean = {}
        for k, v in (row.items() if isinstance(row, dict) else enumerate(row)):
            if isinstance(v, (datetime, date_type)):
                clean[k] = v.isoformat()
            elif isinstance(v, float) and (v != v or math.isinf(v)):
                clean[k] = None
            elif hasattr(v, "hex"):
                clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


# ============================================================================
# Node 1: Identify data sources
# ============================================================================

def identify_sources_node(state: NLQueryState) -> dict:
    """Determine which database to query based on the question."""
    question = state["question"]
    logger.info(f"Identifying data source for: {question[:100]}")

    llm = _get_llm("fast", temperature=0.0)

    prompt = f"""You are a database routing expert. Given a natural language question, determine
which database to query.

Available databases:
1. **postgres** — Employee profiles, teams, projects, assignments, workload allocation
2. **clickhouse** — Event logs (commits, PRs, deploys), DORA metrics, activity data
3. **neo4j** — Collaboration graphs, team relationships (limited data, prefer others)

Question: "{question}"

Respond with ONLY a JSON object (no other text):
{{"database": "postgres|clickhouse|neo4j", "reason": "brief explanation"}}
"""

    try:
        log_llm_call(logger, "router", prompt_preview=question[:100])
        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()
        # Parse JSON
        data = _parse_json_object(text)
        db = data.get("database", "postgres").lower()
        if db not in ("postgres", "clickhouse", "neo4j"):
            db = "postgres"
        reason = data.get("reason", "Default routing")
        logger.info(f"Target DB: {db} ({reason})")
        return {"target_db": db, "db_reason": reason}
    except Exception as e:
        logger.error(f"Source identification failed: {e}")
        # Heuristic fallback
        q_lower = question.lower()
        if any(w in q_lower for w in ["deploy", "commit", "event", "dora", "metric", "velocity", "pr "]):
            return {"target_db": "clickhouse", "db_reason": "Keyword match fallback"}
        if any(w in q_lower for w in ["collaborat", "graph", "relationship", "network"]):
            return {"target_db": "neo4j", "db_reason": "Keyword match fallback"}
        return {"target_db": "postgres", "db_reason": "Default fallback"}


# ============================================================================
# Node 2: Generate query
# ============================================================================

def generate_query_node(state: NLQueryState) -> dict:
    """Generate SQL or Cypher query from natural language."""
    question = state["question"]
    target_db = state["target_db"]
    logger.info(f"Generating query for {target_db}: {question[:80]}")

    # Select schema context
    if target_db == "clickhouse":
        schema = CLICKHOUSE_SCHEMA
        query_lang = "sql"
        db_notes = "Use ClickHouse SQL syntax. Functions: countIf(), sumIf(), toDate(), now(), INTERVAL. No ILIKE — use lower() + LIKE."
    elif target_db == "neo4j":
        schema = NEO4J_SCHEMA
        query_lang = "cypher"
        db_notes = "Use Cypher query syntax. MATCH, WHERE, RETURN, ORDER BY, LIMIT."
    else:
        schema = POSTGRES_SCHEMA
        query_lang = "sql"
        db_notes = "Use PostgreSQL syntax. Supports ILIKE, ARRAY_AGG, window functions. UUIDs are TEXT."

    llm = _get_llm("primary", temperature=0.0)

    prompt = f"""You are an expert database query generator. Generate a {query_lang.upper()} query
to answer the user's question.

DATABASE SCHEMA:
{schema}

IMPORTANT NOTES:
{db_notes}

USER QUESTION: "{question}"

{f"PREVIOUS ERROR (fix this): {state.get('execution_error', '')}" if state.get('execution_error') else ""}

Generate ONLY the query inside a code block. No explanation.
```{query_lang}
"""

    try:
        log_llm_call(logger, "query-gen", prompt_preview=question[:100])
        response = llm.invoke([
            SystemMessage(content=f"You generate precise {query_lang.upper()} queries. Output ONLY the query in a code block."),
            HumanMessage(content=prompt),
        ])
        query = _extract_code_block(response.content)
        logger.info(f"Generated {query_lang}: {query[:120]}...")
        return {"generated_query": query, "query_language": query_lang}
    except Exception as e:
        logger.error(f"Query generation failed: {e}")
        return {"generated_query": "", "query_language": query_lang, "status": "error"}


# ============================================================================
# Node 3: Validate query
# ============================================================================

def validate_query_node(state: NLQueryState) -> dict:
    """Validate the generated query against the schema."""
    query = state.get("generated_query", "")
    target_db = state["target_db"]
    logger.info(f"Validating {state.get('query_language', 'sql')} query")

    if not query:
        return {"validation_result": "Error: Empty query generated"}

    # Basic structural validation
    issues = []
    q_upper = query.upper()

    if state.get("query_language") == "sql":
        # Check for dangerous operations
        if any(kw in q_upper for kw in ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE"]):
            issues.append("Query contains destructive operations (DROP/DELETE/ALTER)")

        # Check table references against schema
        if target_db == "postgres":
            valid_tables = {"employees", "teams", "projects", "project_assignments", "embeddings"}
            # Simple check: extract FROM/JOIN table names
            table_refs = re.findall(r"(?:FROM|JOIN)\s+(\w+)", query, re.IGNORECASE)
            for t in table_refs:
                if t.lower() not in valid_tables:
                    issues.append(f"Unknown table: {t}")

            # Check for common schema errors
            if "team_id" in query.lower() and "projects" in query.lower() and "employees" not in query.lower():
                issues.append("projects table has NO team_id column — only employees has team_id")

        elif target_db == "clickhouse":
            valid_tables = {"events", "dora_daily_metrics"}
            table_refs = re.findall(r"(?:FROM|JOIN)\s+(\w+)", query, re.IGNORECASE)
            for t in table_refs:
                if t.lower() not in valid_tables:
                    issues.append(f"Unknown ClickHouse table: {t}")

    elif state.get("query_language") == "cypher":
        if any(kw in q_upper for kw in ["DELETE", "DETACH", "REMOVE", "SET "]):
            issues.append("Cypher query contains mutating operations")

    if issues:
        result = "Invalid: " + "; ".join(issues)
        logger.warning(f"Validation failed: {result}")
        return {"validation_result": result}

    # LLM-based semantic validation
    try:
        llm = _get_llm("fast", temperature=0.0)
        schema = (POSTGRES_SCHEMA if target_db == "postgres"
                  else CLICKHOUSE_SCHEMA if target_db == "clickhouse"
                  else NEO4J_SCHEMA)

        val_prompt = f"""Check this {state.get('query_language', 'sql').upper()} query for correctness:

SCHEMA:
{schema}

QUERY:
{query}

ORIGINAL QUESTION: "{state['question']}"

Check for:
1. Column names exist in the referenced tables
2. JOIN conditions are valid
3. Query answers the original question
4. Syntax is valid for {'ClickHouse SQL' if target_db == 'clickhouse' else 'PostgreSQL' if target_db == 'postgres' else 'Neo4j Cypher'}

Respond with ONLY: "VALID" if correct, or "INVALID: [specific issues]" if wrong.
"""
        response = llm.invoke([HumanMessage(content=val_prompt)])
        result = response.content.strip()

        if result.upper().startswith("VALID"):
            logger.info("Query validated ✓")
            return {"validation_result": "valid"}
        else:
            logger.warning(f"LLM validation: {result[:120]}")
            return {"validation_result": result}

    except Exception as e:
        # If LLM validation fails, pass through (structural validation passed)
        logger.warning(f"LLM validation unavailable, passing through: {e}")
        return {"validation_result": "valid"}


# ============================================================================
# Node 4: Execute query
# ============================================================================

def execute_query_node(state: NLQueryState) -> dict:
    """Execute the validated query against the target database."""
    query = state["generated_query"]
    target_db = state["target_db"]
    logger.info(f"Executing {state.get('query_language')} on {target_db}")

    try:
        if target_db == "postgres":
            pg = get_postgres_client()
            rows = pg.execute_query(query)
            results = _safe_serialise(rows)
        elif target_db == "clickhouse":
            ch = get_clickhouse_client()
            rows = ch.execute_query(query)
            results = _safe_serialise(rows)
        elif target_db == "neo4j":
            # Neo4j execution — try if available
            from agents.utils.db_clients import get_neo4j_client
            neo4j = get_neo4j_client()
            rows = neo4j.execute_query(query)
            results = _safe_serialise(rows) if rows else []
        else:
            return {"execution_error": f"Unknown database: {target_db}", "status": "error"}

        logger.info(f"Query returned {len(results)} rows")
        return {"query_results": results, "execution_error": ""}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Query execution failed: {error_msg[:200]}")
        return {"query_results": [], "execution_error": error_msg}


# ============================================================================
# Node 5: Fix query (self-correction)
# ============================================================================

def fix_query_node(state: NLQueryState) -> dict:
    """Fix a failed or invalid query using the error message."""
    retry = state.get("retry_count", 0) + 1
    error = state.get("execution_error") or state.get("validation_result", "")
    logger.info(f"Fixing query (attempt {retry}/{MAX_RETRIES}): {error[:120]}")

    llm = _get_llm("primary", temperature=0.0)

    schema = (POSTGRES_SCHEMA if state["target_db"] == "postgres"
              else CLICKHOUSE_SCHEMA if state["target_db"] == "clickhouse"
              else NEO4J_SCHEMA)

    prompt = f"""The following {state.get('query_language', 'sql').upper()} query has an error.
Fix it based on the error message.

ORIGINAL QUESTION: "{state['question']}"

CURRENT QUERY:
```
{state['generated_query']}
```

ERROR: {error}

DATABASE SCHEMA:
{schema}

Generate ONLY the corrected query inside a code block. No explanation.
"""

    try:
        log_llm_call(logger, "query-fix", prompt_preview=f"Retry {retry}: {error[:80]}")
        response = llm.invoke([
            SystemMessage(content="Fix the database query. Output ONLY the corrected query."),
            HumanMessage(content=prompt),
        ])
        fixed = _extract_code_block(response.content)
        logger.info(f"Fixed query: {fixed[:120]}...")
        return {"generated_query": fixed, "retry_count": retry}
    except Exception as e:
        logger.error(f"Query fix failed: {e}")
        return {"retry_count": retry, "status": "error"}


# ============================================================================
# Node 6: Summarize results
# ============================================================================

def summarize_node(state: NLQueryState) -> dict:
    """Translate raw query results into a natural language summary."""
    results = state.get("query_results", [])
    question = state["question"]
    logger.info(f"Summarizing {len(results)} results for: {question[:80]}")

    if not results:
        summary = (
            f"The query returned no results. This could mean:\n"
            f"- No data matches the criteria in your question\n"
            f"- The relevant data hasn't been recorded yet\n\n"
            f"**Query used ({state['target_db']}):**\n"
            f"```{state.get('query_language', 'sql')}\n{state['generated_query']}\n```"
        )
        return {"summary": summary, "status": "ok"}

    llm = _get_llm("primary", temperature=0.3)

    # Truncate results for prompt
    results_str = json.dumps(results[:30], indent=2, default=str)[:3000]

    prompt = f"""Summarize these database query results as a clear, executive-level answer
to the original question.

ORIGINAL QUESTION: "{question}"

DATABASE: {state['target_db']}
QUERY USED:
```{state.get('query_language', 'sql')}
{state['generated_query']}
```

RAW RESULTS ({len(results)} rows):
{results_str}

Guidelines:
- Lead with the direct answer to the question
- Include specific numbers and names from the results
- If there are trends or notable patterns, highlight them
- Keep it concise (2-4 paragraphs max)
- Use bullet points for lists of items
- Include the total row count if relevant
"""

    try:
        log_llm_call(logger, "summarize", prompt_preview=question[:100])
        response = llm.invoke([
            SystemMessage(content="You create clear, data-driven executive summaries from database results."),
            HumanMessage(content=prompt),
        ])
        summary = response.content.strip()
        logger.info(f"Summary generated ({len(summary)} chars)")
        return {"summary": summary, "status": "ok"}
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        # Fallback: format results directly
        summary = f"**Results for:** {question}\n\n"
        summary += f"Query returned {len(results)} rows from {state['target_db']}.\n\n"
        for i, row in enumerate(results[:10]):
            summary += f"- {json.dumps(row, default=str)}\n"
        if len(results) > 10:
            summary += f"\n... and {len(results) - 10} more rows."
        return {"summary": summary, "status": "ok"}


# ============================================================================
# Routing functions
# ============================================================================

def route_after_validation(state: NLQueryState) -> str:
    """Route based on validation result."""
    v = state.get("validation_result", "")
    if v == "valid":
        return "execute"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        logger.warning(f"Max retries ({MAX_RETRIES}) reached, giving up")
        return "give_up"
    return "fix"


def route_after_execution(state: NLQueryState) -> str:
    """Route based on execution result."""
    if state.get("execution_error"):
        if state.get("retry_count", 0) >= MAX_RETRIES:
            return "give_up"
        return "fix"
    return "summarize"


def give_up_node(state: NLQueryState) -> dict:
    """Generate an error summary when all retries are exhausted."""
    logger.warning("Pipeline exhausted retries — generating error summary")
    error = state.get("execution_error") or state.get("validation_result", "Unknown error")
    summary = (
        f"❌ **Unable to answer:** {state['question']}\n\n"
        f"I tried to query {state['target_db']} but encountered persistent errors "
        f"after {state.get('retry_count', 0)} attempts.\n\n"
        f"**Last error:** {error[:300]}\n\n"
        f"**Last query attempted:**\n"
        f"```{state.get('query_language', 'sql')}\n{state.get('generated_query', 'N/A')}\n```\n\n"
        f"You may want to rephrase your question or check if the required data exists."
    )
    return {"summary": summary, "status": "max_retries"}


# ============================================================================
# Graph Builder
# ============================================================================

_graph = None


def get_nl_query_graph():
    """Build and cache the NL→Query LangGraph."""
    global _graph
    if _graph is not None:
        return _graph

    logger.info("Building NL→Query sub-graph...")
    workflow = StateGraph(NLQueryState)

    # Add nodes
    workflow.add_node("identify_sources", identify_sources_node)
    workflow.add_node("generate_query", generate_query_node)
    workflow.add_node("validate_query", validate_query_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_node("fix_query", fix_query_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("give_up", give_up_node)

    # Edges
    workflow.set_entry_point("identify_sources")
    workflow.add_edge("identify_sources", "generate_query")
    workflow.add_edge("generate_query", "validate_query")

    # Conditional: after validation
    workflow.add_conditional_edges(
        "validate_query",
        route_after_validation,
        {"execute": "execute_query", "fix": "fix_query", "give_up": "give_up"},
    )

    # Conditional: after execution
    workflow.add_conditional_edges(
        "execute_query",
        route_after_execution,
        {"summarize": "summarize", "fix": "fix_query", "give_up": "give_up"},
    )

    # Fix loops back to validation
    workflow.add_edge("fix_query", "validate_query")

    # Terminal nodes
    workflow.add_edge("summarize", END)
    workflow.add_edge("give_up", END)

    _graph = workflow.compile()
    logger.info("✓ NL→Query graph compiled")
    return _graph


# ============================================================================
# Public API
# ============================================================================

def nl_query(question: str) -> dict:
    """
    Answer a natural language question by generating and executing a database query.

    Args:
        question: Natural language question about the engineering data.

    Returns:
        dict with keys: summary, generated_query, query_language,
                        target_db, query_results, status
    """
    graph = get_nl_query_graph()

    initial_state: NLQueryState = {
        "question": question,
        "target_db": "",
        "db_reason": "",
        "generated_query": "",
        "query_language": "sql",
        "validation_result": "",
        "query_results": [],
        "execution_error": "",
        "summary": "",
        "retry_count": 0,
        "status": "ok",
    }

    logger.info(f"🔍 NL→Query: {question}")
    final_state = graph.invoke(initial_state)

    return {
        "summary": final_state.get("summary", ""),
        "generated_query": final_state.get("generated_query", ""),
        "query_language": final_state.get("query_language", "sql"),
        "target_db": final_state.get("target_db", ""),
        "query_results": final_state.get("query_results", []),
        "status": final_state.get("status", "ok"),
        "retry_count": final_state.get("retry_count", 0),
    }


# ============================================================================
# Helpers
# ============================================================================

def _parse_json_object(text: str) -> dict:
    """Robustly parse a JSON object from LLM output."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding a JSON object
    m = re.search(r"\{[^}]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}
