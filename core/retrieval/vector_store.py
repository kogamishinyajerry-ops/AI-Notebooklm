from __future__ import annotations

import chromadb
from chromadb.config import Settings
import uuid

class VectorStoreAdapter:
    """
    Adapter for local vector storage using ChromaDB.
    Ensures data privacy (C1) by running as a local persistent library.
    """
    def __init__(self, persist_directory: str = "data/vector_db"):
        settings = Settings(anonymized_telemetry=False)
        self.client = chromadb.PersistentClient(path=persist_directory, settings=settings)
        self.collection_name = "doc_knowledge_base"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def new_document_ids(self, count: int) -> list[str]:
        return [str(uuid.uuid4()) for _ in range(count)]

    def add_documents(
        self,
        chunks: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
        ids: list[str] | None = None,
    ) -> list[str]:
        """
        Adds text chunks with metadata and embeddings to the store.
        Metadata should include: source_file, page_number, bbox.
        """
        ids = ids or self.new_document_ids(len(chunks))
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=chunks
        )
        return ids

    def delete(self, ids: list[str]):
        """Deletes documents by id for transaction rollback."""
        if ids:
            self.collection.delete(ids=ids)

    def query(self, query_embeddings: list[float], top_k: int = 5):
        """
        Queries the store for the most relevant chunks.
        """
        results = self.collection.query(
            query_embeddings=[query_embeddings],
            n_results=top_k
        )
        return results
