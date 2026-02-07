"""
Pinecone Embedding Service

Uses Pinecone's Inference API to generate embeddings with llama-text-embed-v2 model.
Embeddings are stored in PostgreSQL pgvector, not in Pinecone's vector database.
"""

from pinecone.grpc import PineconeGRPC as Pinecone
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class EmbeddingService:
    """Service for generating embeddings using Pinecone's inference API."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-text-embed-v2"):
        """
        Initialize the embedding service.
        
        Args:
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            model: Embedding model to use (default: llama-text-embed-v2)
        """
        self.api_key = api_key or os.getenv("PINECONE_API_KEY")
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        self.model = model
        self.client = Pinecone(api_key=self.api_key)
        self.dimensions = 1024  # llama-text-embed-v2 produces 1024-dimensional vectors
    
    def embed_text(self, text: str, input_type: str = "passage") -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            input_type: Type of input ("passage" or "query")
        
        Returns:
            List of floats representing the embedding vector (1536 dimensions)
        """
        embeddings = self.embed_texts([text], input_type=input_type)
        return embeddings[0]
    
    def embed_texts(self, texts: List[str], input_type: str = "passage") -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            input_type: Type of input ("passage" for storage, "query" for search)
        
        Returns:
            List of embedding vectors, each with 1536 dimensions
        """
        if not texts:
            return []
        
        try:
            # Call Pinecone inference API
            response = self.client.inference.embed(
                model=self.model,
                inputs=texts,
                parameters={"input_type": input_type, "truncate": "END"}
            )
            
            # Extract embeddings from response
            embeddings = [item['values'] for item in response]
            
            # Validate dimensions
            for i, emb in enumerate(embeddings):
                if len(emb) != self.dimensions:
                    raise ValueError(
                        f"Embedding {i} has {len(emb)} dimensions, expected {self.dimensions}"
                    )
            
            return embeddings
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {str(e)}")
    
    def embed_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate embeddings for documents with metadata.
        
        Args:
            documents: List of dicts with 'id', 'text', and optional metadata
        
        Returns:
            List of dicts with 'id', 'text', 'embedding', and metadata
        """
        texts = [doc['text'] for doc in documents]
        embeddings = self.embed_texts(texts, input_type="passage")
        
        result = []
        for i, doc in enumerate(documents):
            result.append({
                **doc,
                'embedding': embeddings[i]
            })
        
        return result


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def embed_text(text: str, input_type: str = "passage") -> List[float]:
    """
    Convenience function to embed a single text.
    
    Args:
        text: Text to embed
        input_type: "passage" for storage, "query" for search
    
    Returns:
        Embedding vector (1536 dimensions)
    """
    service = get_embedding_service()
    return service.embed_text(text, input_type=input_type)


def embed_texts(texts: List[str], input_type: str = "passage") -> List[List[float]]:
    """
    Convenience function to embed multiple texts.
    
    Args:
        texts: List of texts to embed
        input_type: "passage" for storage, "query" for search
    
    Returns:
        List of embedding vectors (each 1536 dimensions)
    """
    service = get_embedding_service()
    return service.embed_texts(texts, input_type=input_type)


# Example usage
if __name__ == "__main__":
    # Test embedding generation
    sample_texts = [
        "Apple is a popular fruit known for its sweetness and crisp texture.",
        "The tech company Apple is known for its innovative products like the iPhone.",
        "Many people enjoy eating apples as a healthy snack.",
    ]
    
    service = EmbeddingService()
    embeddings = service.embed_texts(sample_texts)
    
    print(f"Generated {len(embeddings)} embeddings")
    print(f"Each embedding has {len(embeddings[0])} dimensions")
    print(f"\nFirst embedding (truncated): {embeddings[0][:10]}...")
