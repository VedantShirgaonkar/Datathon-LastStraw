"""
Inspect PostgreSQL database schema.
Run this to see what tables and structure exist.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from postgres.postgres_client import PostgresClient


def inspect_database():
    """Inspect database schema and structure"""
    
    print("=" * 80)
    print("POSTGRESQL DATABASE INSPECTION")
    print("=" * 80)
    
    try:
        client = PostgresClient()
        
        # Test connection
        print("\n[*] Testing connection...")
        if client.verify_connection():
            print("[OK] Connection successful")
        else:
            print("[FAIL] Connection failed")
            return
        
        # Get server version
        version = client.get_server_version()
        print(f"\n[INFO] PostgreSQL Version:")
        print(f"  {version}")
        
        # Check pgvector extension
        print("\n[*] Checking pgvector extension...")
        has_pgvector = client.check_pgvector_extension()
        if has_pgvector:
            print("[OK] pgvector extension is installed")
        else:
            print("[WARN] pgvector extension is NOT installed")
            print("   To install: CREATE EXTENSION vector;")
        
        # List all tables
        print("\n[INFO] Tables in database:")
        tables = client.list_tables()
        
        if not tables:
            print("  (No tables found)")
        else:
            for table in tables:
                row_count = client.get_table_row_count(table)
                print(f"  - {table} ({row_count:,} rows)")
        
        # Get schema for each table
        if tables:
            print("\n" + "=" * 80)
            print("TABLE SCHEMAS")
            print("=" * 80)
            
            for table in tables:
                print(f"\n[TABLE] {table}")
                print("-" * 80)
                
                schema = client.get_table_schema(table)
                
                print(f"{'Column':<30} {'Type':<20} {'Nullable':<10} {'Default':<20}")
                print("-" * 80)
                
                for col in schema:
                    col_name = col['column_name']
                    data_type = col['data_type']
                    
                    # Add length for varchar
                    if col['character_maximum_length']:
                        data_type = f"{data_type}({col['character_maximum_length']})"
                    
                    nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
                    default = col['column_default'] or "-"
                    
                    print(f"{col_name:<30} {data_type:<20} {nullable:<10} {default:<20}")
                
                # Get sample data
                print(f"\n[DATA] Sample data (first 3 rows):")
                try:
                    sample = client.execute_query(f"SELECT * FROM {table} LIMIT 3;")
                    if sample:
                        for i, row in enumerate(sample, 1):
                            print(f"\n  Row {i}:")
                            for key, value in row.items():
                                # Truncate long values
                                if isinstance(value, str) and len(value) > 100:
                                    value = value[:100] + "..."
                                print(f"    {key}: {value}")
                    else:
                        print("    (No data)")
                except Exception as e:
                    print(f"    Error fetching sample: {e}")
        
        client.close()
        
        print("\n" + "=" * 80)
        print("INSPECTION COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    inspect_database()
