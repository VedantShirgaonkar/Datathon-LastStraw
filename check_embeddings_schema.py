import sys
sys.path.insert(0, 'postgres')
from postgres_client import PostgresClient

c = PostgresClient()
c.connect()

# Check indexes
result = c.execute_query("""
    SELECT indexname, indexdef 
    FROM pg_indexes 
    WHERE tablename = 'embeddings';
""")

print("Indexes on embeddings table:")
for r in result:
    print(f"  {r['indexname']}: {r['indexdef']}")

# Check constraints
result = c.execute_query("""
    SELECT conname, contype, pg_get_constraintdef(oid) as definition
    FROM pg_constraint
    WHERE conrelid = 'embeddings'::regclass;
""")

print("\nConstraints on embeddings table:")
for r in result:
    print(f"  {r['conname']} ({r['contype']}): {r['definition']}")

c.close()
