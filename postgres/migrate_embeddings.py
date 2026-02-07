"""
Migrate embeddings table from 1536 to 1024 dimensions for llama-text-embed-v2 model.

This will:
1. Delete existing 1536-dimension embeddings
2. Alter the vector column to 1024 dimensions
3. Recreate indexes for the new dimension
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from postgres.postgres_client import PostgresClient

def migrate_embeddings():
    client = PostgresClient()
    
    print("=" * 60)
    print("MIGRATING EMBEDDINGS TABLE: 1536 -> 1024 dimensions")
    print("=" * 60)
    
    # Step 1: Count existing embeddings
    result = client.execute_query("SELECT COUNT(*) as count FROM embeddings;")
    count = result[0]['count']
    print(f"\n1. Found {count} existing embeddings (will be deleted)")
    
    if count > 0:
        confirm = input(f"\n   Delete {count} embeddings and migrate to 1024 dims? (yes/no): ")
        if confirm.lower() != 'yes':
            print("   Migration cancelled.")
            client.close()
            return
    
    # Step 2: Delete existing embeddings
    print("\n2. Deleting existing embeddings...")
    client.execute_write("DELETE FROM embeddings;")
    print("   ✅ Deleted all embeddings")
    
    # Step 3: Drop existing index
    print("\n3. Dropping existing vector index...")
    try:
        client.execute_write("DROP INDEX IF EXISTS idx_embeddings_vector;")
        print("   ✅ Dropped index")
    except Exception as e:
        print(f"   ⚠️  Index may not exist: {e}")
    
    # Step 4: Alter column to vector(1024)
    print("\n4. Altering embedding column to vector(1024)...")
    client.execute_write("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(1024);")
    print("   ✅ Column altered to 1024 dimensions")
    
    # Step 5: Recreate index for 1024 dimensions
    print("\n5. Creating new IVF-Flat index for 1024 dimensions...")
    client.execute_write("""
        CREATE INDEX idx_embeddings_vector 
        ON embeddings 
        USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100);
    """)
    print("   ✅ Index created")
    
    # Step 6: Verify
    print("\n6. Verifying migration...")
    result = client.execute_query("""
        SELECT 
            a.atttypmod as dimensions
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        WHERE c.relname = 'embeddings' AND a.attname = 'embedding';
    """)
    # atttypmod for vector(1024) would be 1024 + 4 = 1028
    dims = result[0]['dimensions'] - 4 if result else 'unknown'
    print(f"   ✅ Embedding column now has {dims} dimensions")
    
    client.close()
    
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print("\nYou can now use Pinecone's llama-text-embed-v2 model (1024 dims)")
    print("Run: python postgres/test_embeddings.py")


if __name__ == "__main__":
    migrate_embeddings()
