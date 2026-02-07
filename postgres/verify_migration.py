"""Verify the database migration was successful."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    port=os.getenv('POSTGRES_PORT', 5432),
    database=os.getenv('POSTGRES_DATABASE'),
    user=os.getenv('POSTGRES_USERNAME'),
    password=os.getenv('POSTGRES_PASSWORD'),
    sslmode='require'
)
cursor = conn.cursor()

# List all tables
cursor.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' ORDER BY table_name;
""")
tables = [row[0] for row in cursor.fetchall()]
print('=== TABLES IN DATABASE ===')
for t in tables:
    print(f'  {t}')

# Check if key new tables exist
expected_new = ['employees', 'tasks', 'check_ins', 'feedback', 'goals', 'notifications', 'task_events']
print(f'\n=== VERIFICATION ===')
all_ok = True
for tbl in expected_new:
    exists = tbl in tables
    if not exists:
        all_ok = False
    print(f'{"✅" if exists else "❌"} {tbl}: {"EXISTS" if exists else "MISSING"}')

# Show employees table columns
cursor.execute("""
    SELECT column_name, data_type FROM information_schema.columns 
    WHERE table_name = 'employees' ORDER BY ordinal_position;
""")
cols = cursor.fetchall()
if cols:
    print(f'\n=== EMPLOYEES TABLE COLUMNS ===')
    for col in cols:
        print(f'  {col[0]}: {col[1]}')
else:
    print('\n❌ employees table not found!')

# Count rows in tables
print(f'\n=== ROW COUNTS ===')
for tbl in ['employees', 'projects', 'tasks', 'check_ins', 'feedback']:
    if tbl in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        count = cursor.fetchone()[0]
        print(f'  {tbl}: {count} rows')

cursor.close()
conn.close()

print(f'\n{"✅ MIGRATION VERIFIED SUCCESSFULLY!" if all_ok else "❌ SOME TABLES MISSING - CHECK MIGRATION"}')
