"""Quick script to probe the live database schema."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")

from agents.utils.db_clients import get_postgres_client

pg = get_postgres_client()

# 1) Check which person table exists
rows = pg.execute_query(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name IN ('employees', 'users')"
)
print("Person tables found:", [r["table_name"] for r in rows])

# 2) Check columns of each person table found
for tbl in [r["table_name"] for r in rows]:
    cols = pg.execute_query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (tbl,),
    )
    print(f"  {tbl} columns:", [c["column_name"] for c in cols])

# 3) Check project_assignments FK columns
pa_cols = pg.execute_query(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema='public' AND table_name='project_assignments' "
    "ORDER BY ordinal_position"
)
print("project_assignments columns:", [c["column_name"] for c in pa_cols])

# 4) Row counts
for tbl in ["employees", "users", "teams", "projects", "project_assignments"]:
    try:
        cnt = pg.execute_query(f"SELECT count(*) as cnt FROM {tbl}")
        print(f"  {tbl}: {cnt[0]['cnt']} rows")
    except Exception as e:
        print(f"  {tbl}: ERROR - {e}")

# 5) Sample data from person table
person_tbl = rows[0]["table_name"] if rows else "users"
try:
    sample = pg.execute_query(f"SELECT * FROM {person_tbl} LIMIT 2")
    print(f"\nSample from {person_tbl}:")
    for s in sample:
        print(f"  {dict(s)}")
except Exception as e:
    print(f"Sample query error: {e}")
