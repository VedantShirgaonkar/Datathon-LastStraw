"""
Tool package initialization.

Available tool sets:
- neo4j_tools: Graph database operations (5 tools)
- clickhouse_tools: Time-series analytics (5 tools)
- postgres_tools: Entity management + pgvector (8 tools)
- executor_tools: External system commands via Lambda (10 tools)
"""

from agent.tools.neo4j_tools import neo4j_tools
from agent.tools.clickhouse_tools import clickhouse_tools
from agent.tools.postgres_tools import postgres_tools
from agent.tools.executor_tools import executor_tools

# All database tools (for read/write operations)
database_tools = neo4j_tools + clickhouse_tools + postgres_tools

# All tools including executors (28 total)
all_tools = database_tools + executor_tools

__all__ = [
    'neo4j_tools',
    'clickhouse_tools',
    'postgres_tools',
    'executor_tools',
    'database_tools',
    'all_tools'
]
