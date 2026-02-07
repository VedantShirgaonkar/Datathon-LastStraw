"""
Test Pinecone Embedding Service with PostgreSQL pgvector

Demonstrates:
1. Generating embeddings using Pinecone's inference API (llama-text-embed-v2)
2. Storing embeddings in PostgreSQL with pgvector
3. Performing semantic search with cosine similarity
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from postgres.embedding_service import EmbeddingService, embed_text, embed_texts
from agent.tools.postgres_tools import upsert_embedding, search_embeddings
from uuid import uuid4

def test_embedding_generation():
    """Test 1: Generate embeddings using Pinecone"""
    print("\n" + "="*80)
    print("TEST 1: Generate Embeddings with Pinecone")
    print("="*80)
    
    try:
        service = EmbeddingService()
        
        # Sample documents about different topics
        documents = [
            {"id": "doc1", "text": "Apple is a popular fruit known for its sweetness and crisp texture."},
            {"id": "doc2", "text": "The tech company Apple is known for its innovative products like the iPhone."},
            {"id": "doc3", "text": "Many people enjoy eating apples as a healthy snack."},
            {"id": "doc4", "text": "Python is a versatile programming language used for web development and data science."},
            {"id": "doc5", "text": "Machine learning models require large amounts of training data."}
        ]
        
        print(f"\nGenerating embeddings for {len(documents)} documents...")
        embeddings = service.embed_texts([d['text'] for d in documents])
        
        print(f"✅ Generated {len(embeddings)} embeddings")
        print(f"   Each embedding has {len(embeddings[0])} dimensions (llama-text-embed-v2 = 1024)")
        print(f"\n   First embedding (truncated): [{', '.join(f'{x:.6f}' for x in embeddings[0][:5])}...]")
        
        return documents, embeddings
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None, None


def test_store_embeddings(documents, embeddings):
    """Test 2: Store embeddings in PostgreSQL pgvector"""
    print("\n" + "="*80)
    print("TEST 2: Store Embeddings in PostgreSQL pgvector")
    print("="*80)
    
    if not documents or not embeddings:
        print("Skipping - no embeddings to store")
        return []
    
    stored_ids = []
    
    try:
        for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
            source_id = str(uuid4())
            
            result = upsert_embedding(
                embedding_type="document",
                source_id=source_id,
                source_table="test_docs",
                embedding=embedding,
                title=f"Document {doc['id']}",
                content=doc['text'],
                metadata={"doc_id": doc['id'], "index": i}
            )
            
            if result.get('success'):
                print(f"✅ Stored {doc['id']}: {doc['text'][:50]}...")
                stored_ids.append(source_id)
            else:
                print(f"❌ Failed to store {doc['id']}: {result.get('message')}")
        
        print(f"\n✅ Stored {len(stored_ids)} embeddings in PostgreSQL")
        return stored_ids
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return []


def test_text_to_embedding():
    """Test 3: Store embedding by providing text (auto-generation)"""
    print("\n" + "="*80)
    print("TEST 3: Auto-Generate Embedding from Text")
    print("="*80)
    
    try:
        text = "Kafka is a distributed streaming platform for building real-time data pipelines."
        source_id = str(uuid4())
        
        print(f"\nText: {text}")
        print(f"Generating embedding via Pinecone and storing in PostgreSQL...")
        
        result = upsert_embedding(
            embedding_type="document",
            source_id=source_id,
            source_table="test_docs",
            text=text,  # No embedding provided - will auto-generate
            title="Kafka Document",
            metadata={"auto_generated": True}
        )
        
        if result.get('success'):
            print(f"✅ {result.get('message')}")
            print(f"   Embedding ID: {result.get('embedding_id')}")
            print(f"   Dimensions: {result.get('dimensions')}")
            return source_id
        else:
            print(f"❌ Failed: {result.get('message')}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def test_semantic_search_with_embedding():
    """Test 4: Semantic search with pre-computed embedding"""
    print("\n" + "="*80)
    print("TEST 4: Semantic Search (Pre-computed Embedding)")
    print("="*80)
    
    try:
        query = "Tell me about the fruit"
        print(f"\nQuery: {query}")
        print(f"Generating query embedding...")
        
        query_embedding = embed_text(query, input_type="query")
        print(f"✅ Generated query embedding ({len(query_embedding)} dimensions)")
        
        print(f"\nSearching PostgreSQL pgvector with cosine similarity...")
        results = search_embeddings(
            query_embedding=query_embedding,
            embedding_type="document",
            limit=3,
            similarity_threshold=0.5
        )
        
        if results.get('success'):
            matches = results.get('matches', [])
            print(f"✅ Found {len(matches)} matches:")
            for i, match in enumerate(matches, 1):
                print(f"\n   {i}. Similarity: {match['similarity']:.4f}")
                print(f"      Title: {match['title']}")
                print(f"      Content: {match['content'][:60]}...")
        else:
            print(f"❌ Search failed: {results.get('message')}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")


def test_semantic_search_with_text():
    """Test 5: Semantic search by providing text (auto-generation)"""
    print("\n" + "="*80)
    print("TEST 5: Semantic Search (Auto-Generate from Text)")
    print("="*80)
    
    try:
        query_text = "programming languages for developers"
        print(f"\nQuery: {query_text}")
        print(f"Auto-generating query embedding and searching...")
        
        results = search_embeddings(
            query_text=query_text,  # No embedding provided - will auto-generate
            embedding_type="document",
            limit=3,
            similarity_threshold=0.5
        )
        
        if results.get('success'):
            matches = results.get('matches', [])
            print(f"✅ Found {len(matches)} matches:")
            for i, match in enumerate(matches, 1):
                print(f"\n   {i}. Similarity: {match['similarity']:.4f}")
                print(f"      Title: {match['title']}")
                print(f"      Content: {match['content'][:60]}...")
        else:
            print(f"❌ Search failed: {results.get('message')}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")


def cleanup_test_data(stored_ids):
    """Clean up test data"""
    print("\n" + "="*80)
    print("CLEANUP: Remove Test Data")
    print("="*80)
    
    if not stored_ids:
        print("No test data to clean up")
        return
    
    print(f"\nTo clean up, run this SQL:")
    print(f"DELETE FROM embeddings WHERE source_table = 'test_docs';")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("PINECONE EMBEDDING + POSTGRESQL PGVECTOR TEST SUITE")
    print("="*80)
    print("\nArchitecture:")
    print("  1. Pinecone Inference API → Generate embeddings (llama-text-embed-v2)")
    print("  2. PostgreSQL pgvector → Store & search embeddings (cosine similarity)")
    print("="*80)
    
    # Test 1: Generate embeddings
    documents, embeddings = test_embedding_generation()
    
    # Test 2: Store embeddings
    stored_ids = test_store_embeddings(documents, embeddings)
    
    # Test 3: Auto-generate from text
    kafka_id = test_text_to_embedding()
    if kafka_id:
        stored_ids.append(kafka_id)
    
    # Test 4: Search with pre-computed embedding
    test_semantic_search_with_embedding()
    
    # Test 5: Search with text (auto-generation)
    test_semantic_search_with_text()
    
    # Cleanup instructions
    cleanup_test_data(stored_ids)
    
    print("\n" + "="*80)
    print("TEST SUITE COMPLETE")
    print("="*80)
