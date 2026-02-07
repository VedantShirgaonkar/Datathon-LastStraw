"""
Run the unified schema migration against PostgreSQL.

Usage:
    python postgres/run_migration.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def run_migration():
    """Execute the migration SQL file."""
    
    # Read migration SQL
    migration_file = Path(__file__).parent / "migrate_to_unified_schema.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    with open(migration_file, "r", encoding="utf-8") as f:
        migration_sql = f.read()
    
    # Connect to PostgreSQL
    conn_params = {
        "host": os.getenv("POSTGRES_HOST"),
        "port": os.getenv("POSTGRES_PORT", 5432),
        "database": os.getenv("POSTGRES_DATABASE"),
        "user": os.getenv("POSTGRES_USERNAME"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "sslmode": "require"
    }
    
    print(f"🔗 Connecting to {conn_params['host']}:{conn_params['port']}/{conn_params['database']}...")
    
    try:
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = False  # Use transaction
        cursor = conn.cursor()
        
        print("📝 Running migration...")
        
        # Split by semicolon and execute each statement
        # This handles multi-statement SQL files better
        statements = migration_sql.split(';')
        executed = 0
        
        for statement in statements:
            statement = statement.strip()
            if statement and not statement.startswith('--'):
                try:
                    cursor.execute(statement + ';')
                    executed += 1
                except psycopg2.Error as e:
                    # Some errors are OK (like "relation already exists")
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "does not exist" in error_msg:
                        print(f"  ⚠️  Skipped (already applied): {statement[:60]}...")
                        conn.rollback()
                        conn.autocommit = False
                    else:
                        raise
        
        conn.commit()
        print(f"✅ Migration complete! Executed {executed} statements.")
        
        # Verify tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\n📊 Tables in database ({len(tables)}):")
        for table in tables:
            print(f"   • {table}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
