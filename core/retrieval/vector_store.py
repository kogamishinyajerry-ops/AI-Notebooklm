from __future__ import annotations

import chromadb
from chromadb.config import Settings
import json
import uuid


def _serialize_metadata(metadata: dict) -> dict:
    """Normalize metadata for Chroma's scalar-only metadata contract."""
    serialized = dict(metadata)
    bbox = serialized.get("bbox")
    if isinstance(bbox, (list, tuple)):
        serialized["bbox"] = json.dumps(list(bbox))
    return serialized


def _deserialize_metadata(metadata: dict) -> dict:
    """Restore structured fields exposed by the public retrieval contract."""
    restored = dict(metadata)
    bbox = restored.get("bbox")
    if isinstance(bbox, tuple):
        restored["bbox"] = list(bbox)
    elif isinstance(bbox, str):
        try:
            parsed = json.loads(bbox)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            restored["bbox"] = parsed
    return restored


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
            metadatas=[_serialize_metadata(item) for item in metadatas],
            documents=chunks
        )
        return ids

    def delete(self, ids: list[str] | None = None, where: dict | None = None):
        """Deletes documents by id or metadata filter for cleanup."""
        if ids or where:
            self.collection.delete(ids=ids, where=where)

    def query(
        self,
        query_embeddings: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ):
        """
        Queries the store for the most relevant chunks.

        Args:
            query_embeddings: Embedding vector for the query.
            top_k: Number of results to return.
            where: Optional ChromaDB metadata filter, e.g.
                   ``{"source_id": {"$in": ["id1", "id2"]}}``
        """
        kwargs: dict = {
            "query_embeddings": [query_embeddings],
            "n_results": top_k,
        }
        if where:
            kwargs["where"] = where
        results = self.collection.query(**kwargs)
        if results.get("metadatas"):
            results["metadatas"] = [
                [_deserialize_metadata(item) for item in batch]
                for batch in results["metadatas"]
            ]
        return results

    def get_by_ids(self, ids: list[str]) -> dict:
        """
        Fetch documents and metadata by exact Chroma IDs.

        Used by RetrieverEngine._graph_expand() to retrieve real chunk content
        from the knowledge-graph reverse-index.  Returns a dict with keys
        ``documents`` (list[str]) and ``metadatas`` (list[dict]).

        Missing IDs are silently omitted by Chroma; callers must handle an
        empty result gracefully.

        C1 compliant — local Chroma call only, no external network access.
        """
        if not ids:
            return {"documents": [], "metadatas": []}
        result = self.collection.get(ids=ids, include=["documents", "metadatas"])
        return {
            "documents": result.get("documents") or [],
            "metadatas": [
                _deserialize_metadata(item)
                for item in (result.get("metadatas") or [])
            ],
        }

    def get_all(self, where: dict | None = None) -> dict:
        """
        Fetch all documents and metadata, optionally filtered by metadata.

        Primarily used by evaluation tooling to rebuild lexical indexes or
        compute notebook-scoped diagnostics without going through ANN search.
        """
        kwargs: dict = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        result = self.collection.get(**kwargs)
        return {
            "ids": result.get("ids") or [],
            "documents": result.get("documents") or [],
            "metadatas": [
                _deserialize_metadata(item)
                for item in (result.get("metadatas") or [])
            ],
        }
