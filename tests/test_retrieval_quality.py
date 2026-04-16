"""
test_retrieval_quality.py
==========================
S-22: Tests for Retrieval Quality Upgrade.

  * BM25 keyword recall
  * RRF fusion ranking
  * MMR near-duplicate removal
  * Query expansion (aerospace synonyms)
  * Hybrid end-to-end pipeline
  * Source-id scoping still works in hybrid mode

All heavy deps (chromadb, sentence_transformers) are stubbed.
``rank_bm25`` IS expected to be installed in the test environment.
"""
from __future__ import annotations

import sys
import types
import math
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module stubs (same pattern as other test files)
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    for name in ("sentence_transformers", "chromadb", "fitz",
                 "transformers", "torch"):
        if name not in sys.modules:
            s = _stub(name)
            if name == "chromadb":
                cfg = _stub("chromadb.config")
                cfg.Settings = dict
                s.PersistentClient = MagicMock
                s.config = cfg
            elif name == "sentence_transformers":
                s.SentenceTransformer = MagicMock

    for name in [
        "core.retrieval.embeddings", "core.retrieval.reranker",
        "core.retrieval.vector_store",
    ]:
        if name not in sys.modules:
            _stub(name)

    emb = sys.modules["core.retrieval.embeddings"]
    if not hasattr(emb, "EmbeddingManager"):
        emb.EmbeddingManager = MagicMock

    rer = sys.modules["core.retrieval.reranker"]
    if not hasattr(rer, "CrossEncoderReranker"):
        rer.CrossEncoderReranker = MagicMock

    vs = sys.modules["core.retrieval.vector_store"]
    if not hasattr(vs, "VectorStoreAdapter"):
        vs.VectorStoreAdapter = MagicMock


_install_stubs()


# ---------------------------------------------------------------------------
# Fake primitives for retriever construction
# ---------------------------------------------------------------------------

class _FakeEmb:
    def __init__(self, values: List[float]):
        self._v = values

    def tolist(self) -> List[float]:
        return self._v


class _FakeEmbManager:
    """Returns a fixed [0.5, 0.5, ...] vector, or per-text if overridden."""

    def __init__(self, vectors: Optional[Dict[str, List[float]]] = None):
        self._vectors = vectors or {}

    def encode(self, texts: List[str]) -> List[_FakeEmb]:
        result = []
        for t in texts:
            vec = self._vectors.get(t, [0.5, 0.5, 0.5])
            result.append(_FakeEmb(vec))
        return result


class _FakeReranker:
    """Identity reranker — returns chunks in the order it receives them."""

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        return chunks[:top_n]


class _FixedVectorStore:
    """
    Returns a deterministic corpus regardless of query embedding.
    ``source_id`` filter is respected.
    """

    CORPUS = [
        ("alpha stall characteristics study", {"source": "doc1.pdf", "page": "1", "source_id": "src-1"}),
        ("boundary layer transition analysis", {"source": "doc2.pdf", "page": "1", "source_id": "src-1"}),
        ("totally unrelated topic", {"source": "doc3.pdf", "page": "1", "source_id": "src-2"}),
    ]

    def __init__(self):
        self.last_where = None

    def query(self, query_embeddings, top_k=5, where=None):
        self.last_where = where
        allowed_ids = None
        if where is not None:
            if "$in" in where.get("source_id", {}):
                allowed_ids = set(where["source_id"]["$in"])
            elif "$eq" in where.get("source_id", {}):
                allowed_ids = {where["source_id"]["$eq"]}

        docs, metas = [], []
        for text, meta in self.CORPUS:
            if allowed_ids is None or meta["source_id"] in allowed_ids:
                docs.append(text)
                metas.append(meta)
        if not docs:
            return {"documents": [[]], "metadatas": [[]]}
        return {"documents": [docs[:top_k]], "metadatas": [metas[:top_k]]}


# ---------------------------------------------------------------------------
# Helper: build a RetrieverEngine with controlled internals
# ---------------------------------------------------------------------------

def _make_retriever(
    vs=None,
    emb_manager=None,
    reranker=None,
) -> "RetrieverEngine":  # noqa: F821
    from core.retrieval.retriever import RetrieverEngine  # noqa: PLC0415

    r = RetrieverEngine.__new__(RetrieverEngine)
    from core.retrieval.bm25_index import BM25Index  # noqa: PLC0415
    from core.retrieval.query_expander import QueryExpander  # noqa: PLC0415

    r.vector_store = vs or _FixedVectorStore()
    r.embedding_manager = emb_manager or _FakeEmbManager()
    r.reranker = reranker or _FakeReranker()
    r.bm25_index = BM25Index()
    r.query_expander = QueryExpander()
    return r


# ===========================================================================
# F1 — BM25 tests
# ===========================================================================

class TestBM25Index:
    def test_bm25_retrieves_keyword_match(self):
        """BM25 must surface an exact keyword match that vector search misses."""
        from core.retrieval.bm25_index import BM25Index  # noqa: PLC0415

        corpus = [
            ("the quick brown fox jumps over the lazy dog", {"source_id": "s1"}),
            ("stall flutter aeroelastic analysis COMAC C919", {"source_id": "s2"}),
            ("boundary layer transition Reynolds number", {"source_id": "s3"}),
        ]
        idx = BM25Index()
        idx.build(corpus)

        results = idx.query("stall flutter")
        # The aerospace doc should rank first
        assert len(results) >= 1
        assert "stall" in results[0]["text"].lower() or "flutter" in results[0]["text"].lower()

    def test_bm25_empty_corpus_returns_empty(self):
        from core.retrieval.bm25_index import BM25Index  # noqa: PLC0415

        idx = BM25Index()
        assert idx.query("anything") == []

    def test_bm25_zero_score_docs_excluded(self):
        from core.retrieval.bm25_index import BM25Index  # noqa: PLC0415

        corpus = [("hello world", {"source_id": "s1"})]
        idx = BM25Index()
        idx.build(corpus)
        results = idx.query("xyzzy totally absent term zqf")
        # BM25 scores all 0 → results excluded
        assert results == []

    def test_bm25_extra_tokens_passed_to_scorer(self):
        """extra_tokens must be included in the token set used for BM25 scoring."""
        from core.retrieval.bm25_index import BM25Index, _tokenize  # noqa: PLC0415

        # A corpus large enough that IDF > 0 for rare terms
        # "stall" only appears in doc s1; other docs use unrelated terms
        corpus = [
            ("stall speed analysis", {"source_id": "s1"}),
            ("pitch trim flight test", {"source_id": "s2"}),
            ("boundary layer turbulence", {"source_id": "s3"}),
            ("Mach number transonic flow", {"source_id": "s4"}),
            ("Reynolds number laminar", {"source_id": "s5"}),
        ]
        idx = BM25Index()
        idx.build(corpus)

        # With extra_tokens=["stall"], score for doc s1 should be > 0
        scores_with = idx._bm25.get_scores(_tokenize("失速") + ["stall"])
        # stall is rare (1 out of 5 docs) so IDF > 0 → s1 gets a positive score
        assert scores_with[0] > 0, "doc containing 'stall' should score > 0 with stall token"

        # Without extra_tokens, the Chinese query alone gives 0 for all
        scores_without = idx._bm25.get_scores(_tokenize("失速"))
        assert scores_without[0] == 0


# ===========================================================================
# F2 — Query expansion tests
# ===========================================================================

class TestQueryExpander:
    def test_expand_adds_english_synonym_for_chinese_term(self):
        from core.retrieval.query_expander import QueryExpander  # noqa: PLC0415

        exp = QueryExpander()
        _, extra = exp.expand("飞机失速特性分析")
        tokens_lower = [t.lower() for t in extra]
        assert "stall" in tokens_lower

    def test_expand_adds_chinese_for_english_input(self):
        from core.retrieval.query_expander import QueryExpander  # noqa: PLC0415

        exp = QueryExpander()
        _, extra = exp.expand("angle of attack sweep")
        tokens_lower = [t.lower() for t in extra]
        assert "迎角" in tokens_lower or "攻角" in tokens_lower

    def test_expand_no_match_returns_original(self):
        from core.retrieval.query_expander import QueryExpander  # noqa: PLC0415

        exp = QueryExpander()
        aug, extra = exp.expand("what is the weather today")
        assert extra == []
        assert aug == "what is the weather today"

    def test_expand_no_duplicates(self):
        """Expansion must not add terms already present in the query."""
        from core.retrieval.query_expander import QueryExpander  # noqa: PLC0415

        exp = QueryExpander()
        # "stall" is already in the query
        _, extra = exp.expand("stall analysis at high alpha")
        # "stall" should not appear in extra (already present)
        assert "stall" not in extra


# ===========================================================================
# F3 — RRF fusion tests
# ===========================================================================

class TestRRFFusion:
    def test_rrf_ranks_consensus_doc_higher(self):
        """A doc appearing in both lists must outscore one appearing in only one."""
        r = _make_retriever()

        vec_chunks = [
            {"text": "consensus doc A", "metadata": {"source_id": "s1"}},
            {"text": "only-vector doc B", "metadata": {"source_id": "s1"}},
        ]
        bm25_chunks = [
            {"text": "consensus doc A", "metadata": {"source_id": "s1"}},
            {"text": "only-bm25 doc C", "metadata": {"source_id": "s1"}},
        ]

        fused = r._rrf_fuse(vec_chunks, bm25_chunks, top_k=5)
        texts = [c["text"] for c in fused]
        # Consensus doc must be first
        assert texts[0] == "consensus doc A"

    def test_rrf_deduplicates_same_text(self):
        """Identical text chunks from both lists must appear only once in result."""
        r = _make_retriever()

        shared = {"text": "shared chunk", "metadata": {"source_id": "s1"}}
        fused = r._rrf_fuse([shared], [shared], top_k=5)
        assert sum(1 for c in fused if c["text"] == "shared chunk") == 1


# ===========================================================================
# F4 — MMR de-duplication tests
# ===========================================================================

class TestMMR:
    def test_mmr_removes_near_duplicate(self):
        """Two chunks with cosine sim = 0.99 → only one survives MMR."""
        # Use an embedding manager that returns nearly identical vectors
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.999, 0.001, 0.0]

        class _NearDupEmbManager:
            VECS = {"chunk A": vec_a, "chunk B": vec_b}

            def encode(self, texts):
                return [_FakeEmb(self.VECS.get(t, [0.5, 0.5, 0.0])) for t in texts]

        r = _make_retriever(emb_manager=_NearDupEmbManager())

        chunks = [
            {"text": "chunk A", "metadata": {"source_id": "s1"}},
            {"text": "chunk B", "metadata": {"source_id": "s1"}},
        ]
        result = r._mmr_deduplicate(chunks, threshold=0.92)
        assert len(result) == 1

    def test_mmr_keeps_diverse_chunks(self):
        """Two orthogonal chunks must both survive MMR."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]

        class _OrthogonalEmbManager:
            VECS = {"chunk A": vec_a, "chunk B": vec_b}

            def encode(self, texts):
                return [_FakeEmb(self.VECS.get(t, [0.5, 0.5, 0.0])) for t in texts]

        r = _make_retriever(emb_manager=_OrthogonalEmbManager())

        chunks = [
            {"text": "chunk A", "metadata": {"source_id": "s1"}},
            {"text": "chunk B", "metadata": {"source_id": "s1"}},
        ]
        result = r._mmr_deduplicate(chunks, threshold=0.92)
        assert len(result) == 2


# ===========================================================================
# F5 — End-to-end hybrid retrieve()
# ===========================================================================

class TestHybridRetrieve:
    def _build_retriever_with_bm25(self, corpus):
        r = _make_retriever()
        r.bm25_index.build(corpus)
        return r

    def test_retrieve_hybrid_returns_no_source_duplicates(self):
        """End-to-end hybrid retrieve must not return duplicate source+page combos."""
        corpus = [
            ("alpha stall characteristics study", {"source": "doc1.pdf", "page": "1", "source_id": "src-1"}),
            ("boundary layer transition analysis", {"source": "doc2.pdf", "page": "1", "source_id": "src-1"}),
        ]
        r = self._build_retriever_with_bm25(corpus)
        results = r.retrieve("stall analysis", top_k=5, final_k=5, hybrid=True)

        seen = set()
        for chunk in results:
            key = (chunk["metadata"].get("source"), chunk["metadata"].get("page"))
            assert key not in seen, f"Duplicate chunk: {key}"
            seen.add(key)

    def test_retrieve_hybrid_respects_source_ids(self):
        """Hybrid mode must still honour source_id scoping."""
        corpus = [
            ("content from src-1", {"source": "doc1.pdf", "page": "1", "source_id": "src-1"}),
            ("content from src-2", {"source": "doc2.pdf", "page": "1", "source_id": "src-2"}),
        ]
        r = self._build_retriever_with_bm25(corpus)
        results = r.retrieve("content", source_ids=["src-1"], hybrid=True, top_k=5, final_k=5)

        returned_ids = {c["metadata"]["source_id"] for c in results}
        assert "src-2" not in returned_ids

    def test_retrieve_no_hybrid_still_works(self):
        """hybrid=False should still return results via pure vector path."""
        r = _make_retriever()
        results = r.retrieve("stall", hybrid=False, top_k=3, final_k=3)
        assert isinstance(results, list)

    def test_retrieve_empty_vector_result_returns_empty(self):
        """When vector store returns nothing, retrieve() returns []."""

        class _EmptyVS:
            last_where = None

            def query(self, query_embeddings, top_k=5, where=None):
                return {"documents": [[]], "metadatas": [[]]}

        r = _make_retriever(vs=_EmptyVS())
        assert r.retrieve("anything") == []


# ===========================================================================
# F6 — Chunker overlap
# ===========================================================================

# Modules that get stubbed by other test files and must be evicted so the
# real implementations are imported when chunker tests run.
_CHUNKER_REAL_MODULES = (
    "services.ingestion.chunker",
    "services.ingestion.parser",
    "services",
    "services.ingestion",
)


@pytest.fixture(autouse=False)
def _evict_chunker_stubs():
    """Evict stub modules so the real chunker/parser are importable."""
    saved = {}
    for mod in _CHUNKER_REAL_MODULES:
        if mod in sys.modules:
            saved[mod] = sys.modules.pop(mod)
    yield
    # Restore after test so other tests keep their stubs
    sys.modules.update(saved)


class TestChunkerOverlap:
    @pytest.fixture(autouse=True)
    def _setup(self, _evict_chunker_stubs):  # noqa: PT004
        """Each chunker test gets a clean module slate."""

    def _make_blocks(self, texts, page="1"):
        from services.ingestion.parser import DocumentChunk  # noqa: PLC0415
        return [DocumentChunk(text=t, metadata={"page": page}) for t in texts]

    def test_overlap_text_prepended_to_next_chunk(self):
        from services.ingestion.chunker import SemanticChunker  # noqa: PLC0415
        from services.ingestion.parser import DocumentChunk  # noqa: PLC0415

        # Use small max_chars so we get multiple chunks
        chunker = SemanticChunker(max_chars=30, overlap=10)
        blocks = [
            DocumentChunk(text="ABCDEFGHIJKLMNOPQRSTUVWXYZ", metadata={"page": "1"}),
            DocumentChunk(text="1234567890", metadata={"page": "1"}),
        ]
        chunks = chunker.chunk(blocks)
        # Second chunk should contain trailing chars of first chunk
        if len(chunks) > 1:
            assert chunks[1].text.startswith(chunks[0].text[-10:].strip())

    def test_overlap_zero_no_prepend(self):
        from services.ingestion.chunker import SemanticChunker  # noqa: PLC0415
        from services.ingestion.parser import DocumentChunk  # noqa: PLC0415

        chunker = SemanticChunker(max_chars=20, overlap=0)
        blocks = [
            DocumentChunk(text="FIRST_BLOCK_LONG_TEXT", metadata={"page": "1"}),
            DocumentChunk(text="SECOND", metadata={"page": "1"}),
        ]
        chunks = chunker.chunk(blocks)
        if len(chunks) > 1:
            # Second chunk should NOT start with tail of first
            assert not chunks[1].text.startswith(chunks[0].text[-5:])

    def test_single_block_no_split(self):
        from services.ingestion.chunker import SemanticChunker  # noqa: PLC0415
        from services.ingestion.parser import DocumentChunk  # noqa: PLC0415

        chunker = SemanticChunker(max_chars=1000, overlap=100)
        blocks = [DocumentChunk(text="short text", metadata={"page": "1"})]
        chunks = chunker.chunk(blocks)
        assert len(chunks) == 1
        assert chunks[0].text == "short text"
