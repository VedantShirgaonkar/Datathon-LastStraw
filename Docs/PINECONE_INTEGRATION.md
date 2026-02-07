# Pinecone Embedding Integration - Implementation Summary

## Architecture

**Embedding Generation**: Pinecone Inference API (llama-text-embed-v2)  
**Vector Storage & Search**: PostgreSQL pgvector

This hybrid approach provides:
- **Best-in-class embeddings** from Pinecone's llama-text-embed-v2 model (1536 dimensions)
- **Cost-effective storage** in existing PostgreSQL database with pgvector
- **Fast semantic search** using pgvector's IVF-Flat index and cosine similarity

## What Was Built

### 1. Embedding Service (`postgres/embedding_service.py`)
- `EmbeddingService` class for Pinecone inference API integration
- `embed_text()` - Generate embedding for single text
- `embed_texts()` - Batch generate embeddings  
- `embed_documents()` - Generate embeddings with metadata
- Convenience functions: `get_embedding_service()`, `embed_text()`, `embed_texts()`

**Features**:
- Singleton pattern for connection pooling
- Automatic dimension validation (1536)
- Input type differentiation ("passage" for storage, "query" for search)
- Text truncation handling ("END")
- Detailed error messages

### 2. Updated PostgreSQL Tools (`agent/tools/postgres_tools.py`)

#### `upsert_embedding()` - Enhanced
**Old**: Required pre-computed embedding  
**New**: Accept EITHER `embedding` OR `text`

```python
# Option 1: Pre-computed embedding
upsert_embedding(
    embedding_type="documentation",
    source_id="123e4567-e89b-12d3-a456-426614174000",
    source_table="projects",
    embedding=[0.123, -0.456, ...],  # 1536 floats
    title="Project Documentation"
)

# Option 2: Auto-generate from text
upsert_embedding(
    embedding_type="documentation",
    source_id="123e4567-e89b-12d3-a456-426614174000",
    source_table="projects",
    text="This project implements a real-time analytics platform...",
    title="Project Documentation"
)
```

#### `search_embeddings()` - Enhanced
**Old**: Required pre-computed query embedding  
**New**: Accept EITHER `query_embedding` OR `query_text`

```python
# Option 1: Pre-computed query embedding
search_embeddings(
    query_embedding=[0.789, -0.234, ...],  # 1536 floats
    embedding_type="documentation",
    limit=5
)

# Option 2: Auto-generate from query text
search_embeddings(
    query_text="How to implement real-time analytics?",
    embedding_type="documentation",
    limit=5
)
```

### 3. Configuration Updates

#### `.env.example`
```env
# Pinecone (Inference API for Embeddings)
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=engineering-intelligence
```

#### `requirements.txt`
```
pinecone[grpc]>=5.0.0  # Pinecone inference API for embeddings
```

#### `config.py`
- Updated `PineconeConfig` class with proper `__init__`
- Made `PINECONE_ENVIRONMENT` optional (defaults to `us-east-1-aws`)

### 4. Test Suite (`postgres/test_embeddings.py`)

Comprehensive test demonstrating:
1. **Embedding Generation** - Generate 5 embeddings from sample texts
2. **Store Embeddings** - Store pre-computed embeddings in PostgreSQL
3. **Auto-Generate from Text** - Upsert embedding by providing only text
4. **Semantic Search (Pre-computed)** - Search with pre-computed query embedding
5. **Semantic Search (Auto-generate)** - Search by providing query text

## How It Works

### Upsert Flow
```
User provides text
    ↓
embed_text(text, input_type="passage")
    ↓
Pinecone Inference API
    ↓
Returns 1536-dimensional vector
    ↓
PostgreSQL INSERT with pgvector
    ↓
ON CONFLICT UPDATE (upsert behavior)
```

### Search Flow
```
User provides query text
    ↓
embed_text(query_text, input_type="query")
    ↓
Pinecone Inference API
    ↓
Returns query vector
    ↓
PostgreSQL SELECT with cosine similarity
    ↓
ORDER BY embedding <=> query_vector
    ↓
Returns top K matches with similarity scores
```

## Updated Tool Schemas

### UpsertEmbeddingInput
```python
class UpsertEmbeddingInput(BaseModel):
    embedding_type: str                             # Required
    source_id: UUID                                 # Required
    source_table: str                               # Required
    embedding: Optional[List[float]] = None         # Either this...
    text: Optional[str] = None                      # ...or this (required)
    title: str                                      # Required
    content: Optional[str] = None                   # Optional
    metadata: Optional[Dict[str, Any]] = None       # Optional
```

### SearchEmbeddingsInput
```python
class SearchEmbeddingsInput(BaseModel):
    query_embedding: Optional[List[float]] = None   # Either this...
    query_text: Optional[str] = None                # ...or this (required)
    embedding_type: Optional[str] = None            # Optional filter
    limit: int = 10                                 # 1-50
    similarity_threshold: float = 0.7               # 0.0-1.0
```

## Testing

Run the test suite:
```bash
python postgres/test_embeddings.py
```

Expected output:
- ✅ 5 embeddings generated (1536 dimensions each)
- ✅ 5 embeddings stored in PostgreSQL
- ✅ 1 auto-generated embedding from text
- ✅ Semantic search with pre-computed embedding (3 matches)
- ✅ Semantic search with auto-generated query (3 matches)

Cleanup test data:
```sql
DELETE FROM embeddings WHERE source_table = 'test_docs';
```

## Benefits

1. **Flexibility**: Tools accept both pre-computed embeddings AND raw text
2. **Simplicity**: Agents can work with text directly, no embedding pipeline needed
3. **Best Embeddings**: Pinecone's llama-text-embed-v2 provides state-of-the-art quality
4. **Fast Search**: pgvector IVF-Flat index enables millisecond searches
5. **Cost Effective**: Only pay Pinecone for inference, not vector storage
6. **Unified Storage**: All data (entities + vectors) in single PostgreSQL database

## Integration with Agent

The LangGraph agent can now:

1. **Embed Documentation**:
   ```python
   upsert_embedding(
       embedding_type="documentation",
       source_id=project_id,
       source_table="projects",
       text="Project documentation content...",
       title="Project X Documentation"
   )
   ```

2. **Embed Code**:
   ```python
   upsert_embedding(
       embedding_type="code",
       source_id=commit_sha,
       source_table="commits",
       text="def process_data(data): ...",
       title="Data Processing Function"
   )
   ```

3. **Semantic Search**:
   ```python
   search_embeddings(
       query_text="How to process large datasets?",
       embedding_type="documentation",
       limit=5,
       similarity_threshold=0.7
   )
   ```

## Next Steps

1. Add embedding generation to Kafka event pipeline
2. Embed all existing projects and documentation
3. Implement hybrid search (keyword + semantic)
4. Add embedding versioning and updates
5. Monitor Pinecone API usage and costs

## Files Modified/Created

### Created
- `postgres/embedding_service.py` - Pinecone embedding service
- `postgres/test_embeddings.py` - Test suite
- `Docs/PINECONE_INTEGRATION.md` - This document

### Modified
- `agent/tools/postgres_tools.py` - Added text-to-embedding support
- `requirements.txt` - Added pinecone[grpc]>=5.0.0
- `.env.example` - Added Pinecone configuration
- `config.py` - Fixed PineconeConfig class

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                 LangGraph Agent                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  PostgreSQL Tools                           │   │
│  │  • upsert_embedding(text=...)               │   │
│  │  • search_embeddings(query_text=...)        │   │
│  └──────────────┬──────────────────────────────┘   │
└─────────────────┼──────────────────────────────────┘
                  │
      ┌───────────┴──────────┐
      │                      │
      ▼                      ▼
┌──────────────┐      ┌─────────────────┐
│  Pinecone    │      │   PostgreSQL    │
│  Inference   │      │   with pgvector │
│              │      │                 │
│ llama-text-  │      │ • Store vectors │
│  embed-v2    │      │ • IVF-Flat index│
│              │      │ • Cosine search │
│ Generate     │      │ • 15 embeddings │
│ 1536-dim     │      │                 │
│ embeddings   │      │                 │
└──────────────┘      └─────────────────┘
```
