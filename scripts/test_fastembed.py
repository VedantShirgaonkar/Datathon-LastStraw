"""Test fastembed for local embedding generation."""
from fastembed import TextEmbedding

# List available models
print("Available models (sample):")
models = TextEmbedding.list_supported_models()
for m in models[:10]:
    print(f"  {m['model']}: dim={m['dim']}")

# Check for 1024-dim models
print("\n1024-dim models:")
for m in models:
    if m['dim'] == 1024:
        print(f"  {m['model']}: {m['description'][:80]}")

# Test with a model that produces reasonable embeddings
# We'll use a smaller model for now and handle dimension mismatch
print("\nTesting default model...")
embedding_model = TextEmbedding()
embeddings = list(embedding_model.embed(["Senior engineer with Python and Kubernetes expertise"]))
print(f"Embedding dim: {len(embeddings[0])}")
print(f"First 5 values: {embeddings[0][:5]}")
