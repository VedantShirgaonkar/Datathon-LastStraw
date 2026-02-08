"""
Embedding Generation Module
============================
Generates text-to-vector embeddings via the Pinecone Inference API using
NVIDIA's llama-text-embed-v2 model.  This is a lightweight HTTP call —
no local ONNX model or GPU required.

The model produces 1024-dim vectors matching the pgvector column
configuration.  Pinecone's hosted inference handles all the heavy
compute server-side.

Usage:
    from agents.tools.embedding_tools import get_embedding, get_embeddings

    vec = get_embedding("Senior Python engineer with Kubernetes experience")
    vecs = get_embeddings(["text1", "text2", "text3"])
"""

from typing import List, Optional
import os
import numpy as np

from agents.utils.logger import get_logger, log_embedding_call

logger = get_logger(__name__, "EMBEDDINGS")

# ── Configuration ──────────────────────────────────────────────────────

EMBEDDING_MODEL_NAME = "llama-text-embed-v2"
EMBEDDING_DIM = 1024

# Lazy-loaded Pinecone client
_pinecone_client = None


def _get_client():
    """Lazy-load the Pinecone client on first use."""
    global _pinecone_client
    if _pinecone_client is None:
        from pinecone import Pinecone
        api_key = os.getenv("PINECONE_API_KEY", "")
        if not api_key:
            raise ValueError(
                "PINECONE_API_KEY environment variable is required for embedding generation. "
                "Get a free key at https://app.pinecone.io/"
            )
        _pinecone_client = Pinecone(api_key=api_key)
        logger.info(f"✓ Pinecone client initialised (model={EMBEDDING_MODEL_NAME}, dim={EMBEDDING_DIM})")
    return _pinecone_client


def get_embedding(text: str) -> List[float]:
    """
    Generate a single embedding vector for a text string.

    Uses the Pinecone Inference API with llama-text-embed-v2.

    Args:
        text: The text to embed.

    Returns:
        List of floats with length EMBEDDING_DIM (1024).
    """
    vecs = get_embeddings([text])
    return vecs[0]


def get_embeddings(texts: List[str], batch_size: int = 96) -> List[List[float]]:
    """
    Generate embedding vectors for multiple texts via Pinecone Inference.

    Args:
        texts: List of texts to embed.
        batch_size: Texts per API call (Pinecone supports up to 96).

    Returns:
        List of embedding vectors, each with length EMBEDDING_DIM.
    """
    if not texts:
        return []

    pc = _get_client()

    all_vecs: List[List[float]] = []

    # Process in batches (Pinecone limit is 96 inputs per request)
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = pc.inference.embed(
            model=EMBEDDING_MODEL_NAME,
            inputs=[{"text": t} for t in batch],
            parameters={"input_type": "passage", "truncate": "END"},
        )
        for item in response.data:
            all_vecs.append(item["values"])

    log_embedding_call(logger, EMBEDDING_MODEL_NAME, len(texts), EMBEDDING_DIM)
    return all_vecs


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors (for debugging/validation)."""
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


def format_vector_for_pg(vec: List[float]) -> str:
    """Format a vector as a pgvector-compatible string literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
