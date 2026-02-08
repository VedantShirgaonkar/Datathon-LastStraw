"""Check embeddings table structure and existing data."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
from agents.utils.db_clients import get_postgres_client

pg = get_postgres_client()

# Check embeddings table structure
cols = pg.execute_query(
    "SELECT column_name, data_type FROM information_schema.columns "
    "WHERE table_name='embeddings' ORDER BY ordinal_position"
)
print("embeddings columns:")
for c in cols:
    print(f"  {c['column_name']}: {c['data_type']}")

# Count existing embeddings
cnt = pg.execute_query("SELECT count(*) as cnt FROM embeddings")
print(f"\nTotal embeddings: {cnt[0]['cnt']}")

# Check embedding types
types = pg.execute_query(
    "SELECT embedding_type, count(*) as cnt FROM embeddings GROUP BY embedding_type"
)
print("\nEmbedding types:")
for t in types:
    print(f"  {t['embedding_type']}: {t['cnt']}")

# Sample embeddings
try:
    sample = pg.execute_query(
        "SELECT id, embedding_type, source_table, title, "
        "length(content) as content_len, vector_dims(embedding) as dims "
        "FROM embeddings LIMIT 3"
    )
    print("\nSample embeddings:")
    for s in sample:
        print(f"  type={s['embedding_type']}, source={s['source_table']}, "
              f"title={s.get('title','?')}, dims={s['dims']}, content_len={s['content_len']}")
except Exception as e:
    print(f"\nSample query error: {e}")

# Check if Featherless has an embeddings endpoint
print("\n--- Checking embedding API availability ---")
import os
from dotenv import load_dotenv
load_dotenv("/Users/rahul/Desktop/Datathon/.env")
api_key = os.getenv("FEATHERLESS_API_KEY")
base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
print(f"Base URL: {base_url}")
print(f"API Key present: {bool(api_key)}")

# Try embedding endpoint
import httpx
try:
    resp = httpx.post(
        f"{base_url}/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": "test", "model": "intfloat/multilingual-e5-large-instruct"},
        timeout=15,
    )
    print(f"Embedding API status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        dims = len(data["data"][0]["embedding"])
        print(f"Embedding dims: {dims}")
    else:
        print(f"Response: {resp.text[:200]}")
except Exception as e:
    print(f"Embedding API error: {e}")
