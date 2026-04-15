from typing import List, Dict, Any, Optional
from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager
from core.retrieval.reranker import CrossEncoderReranker

class RetrieverEngine:
    """
    Core RAG Retrieval Engine (Task 7)
    Orchestrates initial vector search and subsequent reranking.
    """
    def __init__(self):
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.reranker = CrossEncoderReranker()

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        final_k: int = 3,
        source_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves context chunks for a given query.

        Args:
            query: Natural language question.
            top_k: Candidate count fetched from Chroma before reranking.
            final_k: Number of chunks returned after reranking.
            source_ids: When provided, only chunks whose ``source_id``
                        metadata matches one of the given ids are returned.
                        This enforces per-notebook retrieval isolation.

        Returns:
            List of dicts: {"text": str, "metadata": dict}
        """
        # 1. Embed query
        query_emb = self.embedding_manager.encode([query])[0]

        # 2. Build optional metadata filter for source-scoped retrieval
        where_filter: Optional[dict] = None
        if source_ids:
            if len(source_ids) == 1:
                where_filter = {"source_id": {"$eq": source_ids[0]}}
            else:
                where_filter = {"source_id": {"$in": source_ids}}

        # 3. Vector Search
        # The ChromaDB query returns a dictionary with lists of lists for documents and metadatas
        raw_results = self.vector_store.query(
            query_embeddings=query_emb.tolist(),
            top_k=top_k,
            where=where_filter,
        )

        if not raw_results or not raw_results.get("documents") or not raw_results["documents"][0]:
            return []

        # Format results for reranker
        formatted_chunks = []
        for doc, meta in zip(raw_results["documents"][0], raw_results["metadatas"][0]):
            formatted_chunks.append({
                "text": doc,
                "metadata": meta
            })

        # 4. Rerank
        best_chunks = self.reranker.rerank(query, formatted_chunks, top_n=final_k)
        return best_chunks
