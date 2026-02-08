"""Probe ClickHouse for existing tables and data (fixed parsing)."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
from agents.utils.db_clients import get_clickhouse_client

ch = get_clickhouse_client()

# List all tables (raw query)
result = ch.execute_query("SHOW TABLES")
print("Raw SHOW TABLES result type:", type(result))
print("Raw result:", result)

# Try a different approach
print("\n--- Table details ---")
for table_name in ["events", "dora_daily_metrics"]:
    try:
        desc = ch.execute_query(f"DESCRIBE TABLE {table_name}")
        print(f"\n{table_name} columns:")
        for row in desc:
            print(f"  {row}")
        cnt = ch.execute_query(f"SELECT count() as cnt FROM {table_name}")
        print(f"  Rows: {cnt}")
        sample = ch.execute_query(f"SELECT * FROM {table_name} LIMIT 2")
        print(f"  Sample:")
        for s in sample:
            print(f"    {s}")
    except Exception as e:
        print(f"  Error: {e}")
