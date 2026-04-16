from __future__ import annotations

import math
from typing import List, Dict, Any, Optional

from core.retrieval.vector_store import VectorStoreAdapter
from core.retrieval.embeddings import EmbeddingManager
from core.retrieval.reranker import CrossEncoderReranker
from core.retrieval.bm25_index import BM25Index
from core.retrieval.query_expander import QueryExpander


def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score for a result at position ``rank`` (0-indexed)."""
    return 1.0 / (k + rank + 1)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class RetrieverEngine:
    """
    Core RAG Retrieval Engine — S-22 enhanced with:
      * Hybrid BM25 + vector retrieval fused via RRF
      * Rule-based query expansion (aerospace terminology)
      * MMR diversity de-duplication post-reranking
    """

    def __init__(self) -> None:
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.reranker = CrossEncoderReranker()
        self.bm25_index = BM25Index()
        self.query_expander = QueryExpander()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        final_k: int = 3,
        source_ids: Optional[List[str]] = None,
        hybrid: bool = True,
        expand_query: bool = True,
        mmr_threshold: float = 0.92,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve context chunks for *query*.

        Parameters
        ----------
        query:
            Natural language question (Chinese or English).
        top_k:
            Candidate count fetched from each retrieval source before fusion.
        final_k:
            Number of chunks returned after reranking + MMR.
        source_ids:
            When provided, only chunks whose ``source_id`` metadata field
            matches are considered (per-notebook isolation).
        hybrid:
            When True, fuses BM25 and vector results via RRF before
            reranking.  Falls back gracefully if ``rank_bm25`` is missing.
        expand_query:
            When True, appends aerospace synonym expansions to the query
            used for vector and BM25 retrieval.
        mmr_threshold:
            Cosine-similarity threshold above which near-duplicate chunks
            are dropped after reranking (MMR step).

        Returns
        -------
        List of dicts: ``{"text": str, "metadata": dict}``
        """
        # 1. Optional query expansion
        extra_tokens: List[str] = []
        effective_query = query
        if expand_query:
            effective_query, extra_tokens = self.query_expander.expand(query)

        # 2. Embed (expanded) query
        query_emb = self.embedding_manager.encode([effective_query])[0]
        query_vec: List[float] = query_emb.tolist()

        # 3. Build Chroma source filter
        where_filter: Optional[dict] = None
        if source_ids:
            if len(source_ids) == 1:
                where_filter = {"source_id": {"$eq": source_ids[0]}}
            else:
                where_filter = {"source_id": {"$in": source_ids}}

        # 4. Vector search
        raw = self.vector_store.query(
            query_embeddings=query_vec,
            top_k=top_k,
            where=where_filter,
        )
        vector_chunks: List[Dict[str, Any]] = []
        if raw and raw.get("documents") and raw["documents"][0]:
            for doc, meta in zip(raw["documents"][0], raw["metadatas"][0]):
                vector_chunks.append({"text": doc, "metadata": meta})

        if not vector_chunks:
            return []

        # 5. Hybrid: BM25 fusion
        if hybrid and self.bm25_index.size > 0:
            bm25_results = self.bm25_index.query(
                query, top_k=top_k, extra_tokens=extra_tokens or None
            )
            candidates = self._rrf_fuse(vector_chunks, bm25_results, top_k=top_k)
        else:
            candidates = vector_chunks

        # 6. Rerank
        best_chunks = self.reranker.rerank(query, candidates, top_n=min(final_k * 2, len(candidates)))

        # 7. MMR de-duplication
        if mmr_threshold < 1.0:
            best_chunks = self._mmr_deduplicate(best_chunks, mmr_threshold)

        return best_chunks[:final_k]

    # ------------------------------------------------------------------
    # BM25 index management
    # ------------------------------------------------------------------

    def rebuild_bm25(self, corpus: List[tuple]) -> None:
        """
        Rebuild the in-memory BM25 index from a fresh corpus.
        Called by IngestionService after committing new chunks to ChromaDB.

        Parameters
        ----------
        corpus:
            List of (chunk_text, metadata_dict) tuples.
        """
        self.bm25_index.build(corpus)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rrf_fuse(
        self,
        vector_chunks: List[Dict[str, Any]],
        bm25_chunks: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Merge two ranked lists using Reciprocal Rank Fusion (RRF, k=60).
        Results are deduplicated by text identity.
        """
        scores: Dict[str, float] = {}
        chunks_by_key: Dict[str, Dict[str, Any]] = {}

        def _key(chunk: Dict[str, Any]) -> str:
            return chunk["text"]

        for rank, chunk in enumerate(vector_chunks):
            k = _key(chunk)
            scores[k] = scores.get(k, 0.0) + _rrf_score(rank)
            chunks_by_key[k] = chunk

        for rank, chunk in enumerate(bm25_chunks):
            k = _key(chunk)
            scores[k] = scores.get(k, 0.0) + _rrf_score(rank)
            chunks_by_key.setdefault(k, chunk)

        ranked_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [chunks_by_key[k] for k in ranked_keys[:top_k]]

    def _mmr_deduplicate(
        self,
        chunks: List[Dict[str, Any]],
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """
        Remove near-duplicate chunks whose cosine similarity to a previously
        accepted chunk exceeds *threshold*.

        Embeddings are approximated by bag-of-characters overlap when the
        embedding manager is not available in test contexts.
        """
        if not chunks:
            return chunks

        # Try to get real embeddings; fall back to BoC vectors
        try:
            texts = [c["text"] for c in chunks]
            embeddings = [e.tolist() for e in self.embedding_manager.encode(texts)]
        except Exception:
            # Fallback: simple character n-gram overlap approximation
            embeddings = [self._char_vec(c["text"]) for c in chunks]

        accepted_indices: List[int] = []
        accepted_embs: List[List[float]] = []

        for i, emb in enumerate(embeddings):
            is_duplicate = False
            for acc_emb in accepted_embs:
                try:
                    sim = _cosine_similarity(emb, acc_emb)
                except Exception:
                    sim = 0.0
                if sim > threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                accepted_indices.append(i)
                accepted_embs.append(emb)

        return [chunks[i] for i in accepted_indices]

    @staticmethod
    def _char_vec(text: str, dim: int = 128) -> List[float]:
        """Minimal character-hash bag-of-characters vector for MMR fallback."""
        vec = [0.0] * dim
        for ch in text:
            vec[ord(ch) % dim] += 1.0
        total = sum(vec) or 1.0
        return [v / total for v in vec]
