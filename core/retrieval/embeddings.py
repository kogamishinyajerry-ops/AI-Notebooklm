from __future__ import annotations

import os

from sentence_transformers import SentenceTransformer


def should_use_local_files_only() -> bool:
    value = os.getenv("EMBEDDING_LOCAL_FILES_ONLY")
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("HF_HUB_OFFLINE", "").strip() == "1"
        or os.getenv("TRANSFORMERS_OFFLINE", "").strip() == "1"
    )


class EmbeddingManager:
    """
    Manages local embedding models for semantic search.
    Follows Constraint C1: All models are loaded locally.
    """
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5", local_files_only: bool | None = None):
        local_only = should_use_local_files_only() if local_files_only is None else local_files_only
        try:
            self.model = SentenceTransformer(model_name, local_files_only=local_only)
        except OSError as exc:
            if not local_only:
                raise
            raise RuntimeError(
                f"Embedding model '{model_name}' was not found in the local cache. "
                "Run scripts/pre_download_models.py during the image build or disable offline mode for setup."
            ) from exc

    def encode(self, texts: list[str]):
        """Encodes a list of strings into vectors."""
        return self.model.encode(texts, normalize_embeddings=True)
