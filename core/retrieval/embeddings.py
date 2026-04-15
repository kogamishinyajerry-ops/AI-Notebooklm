import os

from sentence_transformers import SentenceTransformer

class EmbeddingManager:
    """
    Manages local embedding models for semantic search.
    Follows Constraint C1: All models are loaded locally.
    """
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

        cache_folder = os.environ.get("HF_HOME", "models")
        local_model = os.environ.get("EMBEDDING_MODEL_PATH", model_name)

        # C1 requires the embedding model to be pre-baked into local cache / image layers.
        self.model = SentenceTransformer(
            local_model,
            cache_folder=cache_folder,
            local_files_only=True,
        )

    def encode(self, texts: list[str]):
        """Encodes a list of strings into vectors."""
        return self.model.encode(texts, normalize_embeddings=True)
