import chromadb
import uuid
from core.storage.space_resolver import normalize_space_id

class VectorStoreAdapter:
    """
    Adapter for local vector storage using ChromaDB.
    Ensures data privacy (C1) by running as a local persistent library.
    """
    def __init__(self, space_id: str = "default", persist_directory: str = "data/vector_db"):
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection_name = f"space_{normalize_space_id(space_id)}"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def add_documents(self, chunks: list[str], metadatas: list[dict], embeddings: list[list[float]]):
        """
        Adds text chunks with metadata and embeddings to the store.
        Metadata should include: source_file, page_number, bbox.
        """
        ids = [str(uuid.uuid4()) for _ in chunks]
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=chunks
            )
        except Exception:
            try:
                self.delete_documents(ids)
            except Exception:
                pass
            raise
        return ids

    def delete_documents(self, ids: list[str]):
        if not ids:
            return
        self.collection.delete(ids=ids)

    def query(
        self,
        query_embeddings: list[float] = None,
        top_k: int = 5,
        query_embedding: list[float] = None,
    ):
        """
        Queries the store for the most relevant chunks.
        """
        embedding = query_embeddings if query_embeddings is not None else query_embedding
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k
        )
        return results
