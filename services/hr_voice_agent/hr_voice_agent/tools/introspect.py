from __future__ import annotations

import asyncio

from hr_voice_agent.config import get_settings
from hr_voice_agent.clients.postgres_client import PostgresClient, list_tables
from hr_voice_agent.clients.neo4j_client import Neo4jClient


async def _main() -> None:
    s = get_settings()
    print("== HR Voice Agent DB Introspection ==")

    if s.postgres_enabled():
        print("\n[Postgres] enabled")
        pool = await PostgresClient(s.postgres_dsn).connect()
        try:
            tables = await list_tables(pool)
            print(f"tables ({len(tables)}): {', '.join(tables[:60])}{' ...' if len(tables) > 60 else ''}")
        finally:
            await pool.close()
    else:
        print("\n[Postgres] not configured")

    if s.neo4j_enabled():
        print("\n[Neo4j] enabled")
        neo4j = Neo4jClient(uri=s.neo4j_uri, username=s.neo4j_username, password=s.neo4j_password, database=s.neo4j_database)
        try:
            # Basic liveness query
            ctx = neo4j.get_person_graph_context(email=None, user_id=None)
            print("connected (query executed)")
        except Exception as e:
            print(f"connection/query failed: {e}")
        finally:
            neo4j.close()
    else:
        print("\n[Neo4j] not configured")

    if s.pinecone_enabled():
        print("\n[Pinecone] enabled (credentials present)")
        print(f"index: {s.pinecone_index}")
    else:
        print("\n[Pinecone] not configured")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
