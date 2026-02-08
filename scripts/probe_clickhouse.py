"""Probe ClickHouse for existing tables and data."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
from agents.utils.db_clients import get_clickhouse_client

try:
    ch = get_clickhouse_client()
    
    # List all tables
    tables = ch.execute_query("SHOW TABLES")
    print("ClickHouse tables:")
    for t in tables:
        print(f"  {t}")
    
    # Check if events table exists and its schema
    if tables:
        for table_row in tables:
            tbl = table_row[0] if isinstance(table_row, (list, tuple)) else str(table_row)
            print(f"\nSchema for {tbl}:")
            cols = ch.execute_query(f"DESCRIBE TABLE {tbl}")
            for c in cols:
                print(f"  {c}")
            count = ch.execute_query(f"SELECT count() FROM {tbl}")
            print(f"  Row count: {count}")
    
except Exception as e:
    print(f"ClickHouse error: {e}")
    import traceback
    traceback.print_exc()
