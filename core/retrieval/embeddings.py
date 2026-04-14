from sentence_transformers import SentenceTransformer

class EmbeddingManager:
    """
    Manages local embedding models for semantic search.
    Follows Constraint C1: All models are loaded locally.
    """
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        # This will download the model to ~/.cache/torch/sentence_transformers on first run
        # In a strict air-gapped environment, the model weights should be pre-baked.
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]):
        """Encodes a list of strings into vectors."""
        return self.model.encode(texts, normalize_embeddings=True)
