"""Check all new tables and columns in the database."""
import os
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

tables_to_check = [
    'employees', 'tasks', 'task_events', 'task_participants',
    'check_ins', 'one_on_one_notes', 'goals', 'goal_links', 
    'feedback', 'employee_monthly_metrics', 'ci_pipelines',
    'notifications', 'agent_user_preferences', 'agent_review_sessions',
    'data_access_policies'
]

print('=' * 60)
print('NEW TABLES & COLUMNS CHECK')
print('=' * 60)

for tbl in tables_to_check:
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position;
    """, (tbl,))
    cols = cursor.fetchall()
    if cols:
        print(f'\n✅ {tbl.upper()} ({len(cols)} columns)')
        for c in cols:
            nullable = '(nullable)' if c[2] == 'YES' else ''
            print(f'   • {c[0]}: {c[1]} {nullable}')
    else:
        print(f'\n❌ {tbl.upper()}: NOT FOUND')

cursor.close()
conn.close()
print('\n✅ Schema check complete!')
