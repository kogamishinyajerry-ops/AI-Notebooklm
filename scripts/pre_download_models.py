from sentence_transformers import SentenceTransformer

# 1. Pre-download the local embedding model
print("Archiving HuggingFace Embedding Model...")
try:
    SentenceTransformer('BAAI/bge-large-zh-v1.5')
    print("Embedding model successfully cached.")
except Exception as e:
    print(f"Warning: Failed to cache embedding model: {e}")

# Note: Further models (like cross-encoders) can be added here
# to ensure zero runtime network dependency for the COMAC air-gap environment.
