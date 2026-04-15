from typing import List, Dict, Any
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

    def retrieve(self, query: str, top_k: int = 10, final_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves context chunks for a given query.
        Returns a list of dicts: {"text": str, "metadata": dict}
        """
        # 1. Embed query
        query_emb = self.embedding_manager.encode([query])[0]
        
        # 2. Vector Search
        # The ChromaDB query returns a dictionary with lists of lists for documents and metadatas
        raw_results = self.vector_store.query(query_embedding=query_emb.tolist(), top_k=top_k)
        
        if not raw_results or not raw_results.get("documents") or not raw_results["documents"][0]:
            return []
            
        # Format results for reranker
        formatted_chunks = []
        for doc, meta in zip(raw_results["documents"][0], raw_results["metadatas"][0]):
            formatted_chunks.append({
                "text": doc,
                "metadata": meta
            })
            
        # 3. Rerank
        best_chunks = self.reranker.rerank(query, formatted_chunks, top_n=final_k)
        return best_chunks
