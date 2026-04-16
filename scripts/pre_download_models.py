from sentence_transformers import CrossEncoder, SentenceTransformer

# 1. Pre-download the local embedding model
print("Archiving HuggingFace Embedding Model...")
try:
    SentenceTransformer('BAAI/bge-large-zh-v1.5')
    print("Embedding model successfully cached.")
except Exception as e:
    print(f"Warning: Failed to cache embedding model: {e}")

# 2. Pre-download the local reranker model
print("Archiving HuggingFace Reranker Model...")
try:
    CrossEncoder('BAAI/bge-reranker-base')
    print("Reranker model successfully cached.")
except Exception as e:
    print(f"Warning: Failed to cache reranker model: {e}")
