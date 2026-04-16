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
    Core RAG Retrieval Engine — S-22 + Gap-A enhanced with:
      * Hybrid BM25 + vector retrieval fused via RRF
      * Rule-based query expansion (aerospace terminology)
      * MMR diversity de-duplication post-reranking
      * Graph expansion: knowledge-graph entities as third retrieval signal
        (weights: semantic=0.4, bm25=0.3, graph=0.3)
    """

    def __init__(self) -> None:
        self.vector_store = VectorStoreAdapter()
        self.embedding_manager = EmbeddingManager()
        self.reranker = CrossEncoderReranker()
        self.bm25_index = BM25Index()
        self.query_expander = QueryExpander()
        # graph_store and graph_extractor are injected by apps/api/main.py
        # after startup; they default to None so the retriever works without
        # a knowledge graph (gap-A gracefully degrades when not present).
        self.graph_store = None
        self.graph_extractor = None

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
        expand_graph: bool = True,
        notebook_id: Optional[str] = None,
        rrf_weights: Optional[Dict[str, float]] = None,
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
        expand_graph:
            When True (and graph_store/graph_extractor are injected), runs
            graph expansion as a third retrieval signal fused via 3-way RRF.
        notebook_id:
            Required for graph expansion (identifies which graph to query).
        rrf_weights:
            Optional mapping for weighted RRF keys ``semantic``, ``bm25``,
            and ``graph``. Values are normalized automatically when present.

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

        # 5. BM25 retrieval
        bm25_chunks: List[Dict[str, Any]] = []
        if hybrid and self.bm25_index.size > 0:
            try:
                bm25_chunks = self.bm25_index.query(
                    query,
                    top_k=top_k,
                    extra_tokens=extra_tokens or None,
                    source_ids=source_ids,
                )
            except TypeError:
                bm25_chunks = self.bm25_index.query(
                    query,
                    top_k=top_k,
                    extra_tokens=extra_tokens or None,
                )
                if source_ids:
                    allowed_sources = set(source_ids)
                    bm25_chunks = [
                        chunk
                        for chunk in bm25_chunks
                        if chunk.get("metadata", {}).get("source_id") in allowed_sources
                    ]

        # 6. Graph expansion (Gap-A: third retrieval signal)
        graph_chunks: List[Dict[str, Any]] = []
        if expand_graph and notebook_id and self.graph_store and self.graph_extractor:
            graph_chunks = self._graph_expand(
                query,
                notebook_id,
                source_ids=source_ids,
            )

        if not vector_chunks and not bm25_chunks and not graph_chunks:
            return []

        # 7. Fuse signals via RRF
        if bm25_chunks or graph_chunks:
            weights = self._resolve_rrf_weights(rrf_weights)
            candidates = self._rrf_fuse_three_way(
                vector_chunks,
                bm25_chunks,
                graph_chunks,
                top_k=top_k,
                w_semantic=weights["semantic"],
                w_bm25=weights["bm25"],
                w_graph=weights["graph"],
            )
        else:
            candidates = vector_chunks

        if not candidates:
            return []

        # 8. Rerank
        best_chunks = self.reranker.rerank(query, candidates, top_n=min(final_k * 2, len(candidates)))

        # 9. MMR de-duplication
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

    @staticmethod
    def _resolve_rrf_weights(
        rrf_weights: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        defaults = {"semantic": 0.4, "bm25": 0.3, "graph": 0.3}
        if not rrf_weights:
            return defaults

        weights = {
            "semantic": float(rrf_weights.get("semantic", defaults["semantic"])),
            "bm25": float(rrf_weights.get("bm25", defaults["bm25"])),
            "graph": float(rrf_weights.get("graph", defaults["graph"])),
        }
        total = sum(max(value, 0.0) for value in weights.values())
        if total <= 0:
            return defaults

        return {
            key: max(value, 0.0) / total
            for key, value in weights.items()
        }

    def _graph_expand(
        self,
        query: str,
        notebook_id: str,
        source_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gap-A: Use identified query entities to look up associated chunk_ids
        in the knowledge graph, then fetch those chunks from the vector store.

        Returns a list of ``{"text": str, "metadata": dict}`` dicts.
        Returns [] when no graph exists or no entities are found.

        C1 compliant — no LLM calls, no network calls.
        """
        if self.graph_extractor is None or self.graph_store is None:
            return []

        entities = self.graph_extractor.identify_entities(query)
        if not entities:
            return []

        # Collect chunk_ids from the graph's reverse-index for the matched
        # entities and their direct graph neighbours. This lets graph
        # expansion pull in adjacent concepts instead of only exact hits.
        expanded_entities = list(dict.fromkeys(entities))
        if hasattr(self.graph_store, "get_neighbors"):
            try:
                for entity in list(expanded_entities):
                    for neighbour in self.graph_store.get_neighbors(notebook_id, entity, depth=1):
                        if neighbour not in expanded_entities:
                            expanded_entities.append(neighbour)
            except Exception:
                pass

        chunk_ids: List[str] = []
        seen: set = set()
        for entity in expanded_entities:
            for cid in self.graph_store.get_source_chunks(notebook_id, entity):
                if cid not in seen:
                    seen.add(cid)
                    chunk_ids.append(cid)

        if not chunk_ids:
            return []

        # Fetch chunks from the vector store by ID
        try:
            results = self.vector_store.get_by_ids(chunk_ids)
        except Exception:
            return []

        allowed_sources = set(source_ids) if source_ids is not None else None
        chunks: List[Dict[str, Any]] = []
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        for doc, meta in zip(docs, metas):
            metadata = meta or {}
            if (
                allowed_sources is not None
                and metadata.get("source_id") not in allowed_sources
            ):
                continue
            if doc:
                chunks.append({"text": doc, "metadata": metadata})
        return chunks

    def _rrf_fuse_three_way(
        self,
        vector_chunks: List[Dict[str, Any]],
        bm25_chunks: List[Dict[str, Any]],
        graph_chunks: List[Dict[str, Any]],
        top_k: int,
        w_semantic: float = 0.4,
        w_bm25: float = 0.3,
        w_graph: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Merge up to three ranked lists using weighted Reciprocal Rank Fusion.

        Weights: semantic=0.4, bm25=0.3, graph=0.3.
        Missing lists contribute 0 to their weighted score.
        Results are deduplicated by text identity.
        """
        scores: Dict[str, float] = {}
        chunks_by_key: Dict[str, Dict[str, Any]] = {}

        def _key(chunk: Dict[str, Any]) -> str:
            return chunk["text"]

        def _add(ranked: List[Dict[str, Any]], weight: float) -> None:
            for rank, chunk in enumerate(ranked):
                k = _key(chunk)
                scores[k] = scores.get(k, 0.0) + weight * _rrf_score(rank)
                chunks_by_key.setdefault(k, chunk)

        _add(vector_chunks, w_semantic)
        _add(bm25_chunks, w_bm25)
        _add(graph_chunks, w_graph)

        ranked_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [chunks_by_key[k] for k in ranked_keys[:top_k]]

    def _rrf_fuse(
        self,
        vector_chunks: List[Dict[str, Any]],
        bm25_chunks: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        2-way RRF (equal weights). Retained for backward compatibility.
        """
        return self._rrf_fuse_three_way(
            vector_chunks, bm25_chunks, [], top_k,
            w_semantic=0.5, w_bm25=0.5, w_graph=0.0,
        )

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
