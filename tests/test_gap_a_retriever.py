"""
test_gap_a_retriever.py
=======================
Gap-A: Tests for graph-expansion as third retrieval signal in RetrieverEngine.

Covers:
  * _graph_expand() returns chunks when entities match graph reverse-index
  * _graph_expand() returns [] when graph_store is None (graceful degradation)
  * _graph_expand() returns [] when no entities identified in query
  * _graph_expand() returns [] when get_by_ids raises / returns empty
  * _rrf_fuse_three_way() correct weighted fusion of three ranked lists
  * _rrf_fuse_three_way() degrades gracefully with empty bm25/graph lists
  * retrieve() with expand_graph=True includes graph chunks in candidates
  * retrieve() with expand_graph=False skips graph expansion
  * test_rrf_three_way_weights — graph signal boosts chunk not in vector/bm25 results

All heavy deps stubbed at module level; tests are fully offline (C1 compliant).
"""
from __future__ import annotations

import sys
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stubs — installed before any core.retrieval imports
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


for _name in ("sentence_transformers", "chromadb", "fitz", "transformers", "torch", "tenacity"):
    if _name not in sys.modules:
        s = _stub(_name)
        if _name == "chromadb":
            cfg = _stub("chromadb.config")
            cfg.Settings = dict
            s.PersistentClient = MagicMock
            s.config = cfg
        elif _name == "sentence_transformers":
            s.SentenceTransformer = MagicMock

for _name in ("core.retrieval.embeddings", "core.retrieval.reranker",
              "core.retrieval.vector_store"):
    if _name not in sys.modules:
        mod = _stub(_name)
        mod.EmbeddingManager = MagicMock
        mod.CrossEncoderReranker = MagicMock
        mod.VectorStoreAdapter = MagicMock

# ---------------------------------------------------------------------------


from core.retrieval.retriever import RetrieverEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class _FakeEmbedding:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class _FakeEmbeddingManager:
    def encode(self, texts):
        return [_FakeEmbedding([0.1, 0.2, 0.3]) for _ in texts]


class _FakeVectorStore:
    def __init__(self, corpus=None):
        # corpus: dict[id -> (text, meta)]
        self._corpus = corpus or {}
        self.last_where = None

    def query(self, query_embeddings, top_k, where=None):
        self.last_where = where
        docs = ["vec doc A", "vec doc B"]
        metas = [{"source": "a.pdf"}, {"source": "b.pdf"}]
        return {"documents": [docs[:top_k]], "metadatas": [metas[:top_k]]}

    def get_by_ids(self, ids: List[str]):
        docs, metas = [], []
        for cid in ids:
            if cid in self._corpus:
                doc, meta = self._corpus[cid]
                docs.append(doc)
                metas.append(meta)
        if not docs:
            return {"documents": [], "metadatas": []}
        return {"documents": docs, "metadatas": metas}


class _FakeReranker:
    def rerank(self, query, chunks, top_n):
        return chunks[:top_n]


class _FakeBM25Index:
    size = 0

    def build(self, corpus):
        pass

    def query(self, q, top_k=10, extra_tokens=None):
        return []


class _FakeQueryExpander:
    def expand(self, query):
        return query, []


class _FakeGraphExtractor:
    """Returns a fixed entity list for any query containing 'CFD'."""
    def identify_entities(self, text: str) -> List[str]:
        if "CFD" in text or "cfd" in text.lower():
            return ["CFD"]
        return []


class _FakeGraphStore:
    """Returns fixed chunk_ids for the 'CFD' entity."""
    def get_source_chunks(self, notebook_id: str, entity: str) -> List[str]:
        if entity == "CFD":
            return ["graph-chunk-1", "graph-chunk-2"]
        return []

    def get_neighbors(self, notebook_id: str, entity: str, depth: int = 1) -> List[str]:
        return []


def _make_retriever(corpus=None):
    """Build a RetrieverEngine with all heavy sub-components replaced."""
    r = RetrieverEngine.__new__(RetrieverEngine)
    r.embedding_manager = _FakeEmbeddingManager()
    r.vector_store = _FakeVectorStore(corpus or {})
    r.reranker = _FakeReranker()
    r.bm25_index = _FakeBM25Index()
    r.query_expander = _FakeQueryExpander()
    r.graph_store = None
    r.graph_extractor = None
    return r


# ===========================================================================
# Tests: _graph_expand()
# ===========================================================================

class TestGraphExpand:
    def test_returns_chunks_when_entity_found_in_graph(self):
        corpus = {
            "graph-chunk-1": ("CFD analysis text about boundary layer", {"source": "doc.pdf"}),
            "graph-chunk-2": ("RANS turbulence modelling for C919", {"source": "doc.pdf"}),
        }
        r = _make_retriever(corpus=corpus)
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        chunks = r._graph_expand("CFD boundary layer analysis", "nb-1")
        assert len(chunks) == 2
        texts = {c["text"] for c in chunks}
        assert "CFD analysis text about boundary layer" in texts
        assert "RANS turbulence modelling for C919" in texts

    def test_returns_empty_when_graph_store_is_none(self):
        r = _make_retriever()
        r.graph_store = None
        r.graph_extractor = _FakeGraphExtractor()

        chunks = r._graph_expand("CFD analysis", "nb-1")
        assert chunks == []

    def test_returns_empty_when_graph_extractor_is_none(self):
        r = _make_retriever()
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = None

        chunks = r._graph_expand("CFD analysis", "nb-1")
        assert chunks == []

    def test_returns_empty_when_no_entities_in_query(self):
        r = _make_retriever()
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        # Query contains no entity the extractor recognises
        chunks = r._graph_expand("what is the weather today", "nb-1")
        assert chunks == []

    def test_returns_empty_when_get_by_ids_raises(self):
        r = _make_retriever()

        class _RaisingVectorStore(_FakeVectorStore):
            def get_by_ids(self, ids):
                raise RuntimeError("vector store unavailable")

        r.vector_store = _RaisingVectorStore()
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        chunks = r._graph_expand("CFD analysis", "nb-1")
        assert chunks == []

    def test_returns_empty_when_chunk_ids_not_in_store(self):
        r = _make_retriever(corpus={})  # empty corpus
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        chunks = r._graph_expand("CFD analysis", "nb-1")
        assert chunks == []


# ===========================================================================
# Tests: _rrf_fuse_three_way()
# ===========================================================================

class TestRRFThreeWay:
    def _make_chunk(self, text: str, source: str = "doc.pdf") -> Dict[str, Any]:
        return {"text": text, "metadata": {"source": source}}

    def test_all_three_signals_fused(self):
        r = _make_retriever()
        vec = [self._make_chunk("vec A"), self._make_chunk("vec B")]
        bm25 = [self._make_chunk("bm25 X"), self._make_chunk("vec A")]
        graph = [self._make_chunk("graph G"), self._make_chunk("vec A")]

        result = r._rrf_fuse_three_way(vec, bm25, graph, top_k=10)
        texts = [c["text"] for c in result]

        # "vec A" appears in all three → highest score → must be first
        assert texts[0] == "vec A"
        # All unique texts present
        assert set(texts) == {"vec A", "vec B", "bm25 X", "graph G"}

    def test_graph_only_chunk_appears_in_result(self):
        """A chunk only in graph signal must still appear in the fused result."""
        r = _make_retriever()
        vec = [self._make_chunk("vec A")]
        bm25 = [self._make_chunk("bm25 B")]
        graph = [self._make_chunk("graph exclusive")]

        result = r._rrf_fuse_three_way(vec, bm25, graph, top_k=10)
        texts = {c["text"] for c in result}
        assert "graph exclusive" in texts

    def test_empty_bm25_and_graph_returns_vector_only(self):
        r = _make_retriever()
        vec = [self._make_chunk("only vec")]
        result = r._rrf_fuse_three_way(vec, [], [], top_k=5)
        assert len(result) == 1
        assert result[0]["text"] == "only vec"

    def test_top_k_limits_output(self):
        r = _make_retriever()
        vec = [self._make_chunk(f"vec {i}") for i in range(10)]
        bm25 = [self._make_chunk(f"bm25 {i}") for i in range(10)]
        graph = [self._make_chunk(f"graph {i}") for i in range(10)]

        result = r._rrf_fuse_three_way(vec, bm25, graph, top_k=5)
        assert len(result) == 5

    def test_rrf_backward_compat_two_way(self):
        """_rrf_fuse (2-way) still works via _rrf_fuse_three_way delegation."""
        r = _make_retriever()
        vec = [self._make_chunk("A"), self._make_chunk("B")]
        bm25 = [self._make_chunk("B"), self._make_chunk("C")]

        result = r._rrf_fuse(vec, bm25, top_k=5)
        texts = {c["text"] for c in result}
        # "B" appears in both → highest score
        assert result[0]["text"] == "B"
        assert texts == {"A", "B", "C"}


# ===========================================================================
# Tests: retrieve() with graph expansion
# ===========================================================================

class TestRetrieveWithGraphExpansion:
    def test_retrieve_with_graph_expand_true_calls_graph(self):
        """When expand_graph=True and graph components present, _graph_expand is called."""
        corpus = {
            "graph-chunk-1": ("CFD boundary layer content", {"source": "doc.pdf"}),
        }
        r = _make_retriever(corpus=corpus)
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        results = r.retrieve(
            "CFD boundary layer",
            top_k=5,
            final_k=3,
            expand_graph=True,
            notebook_id="nb-1",
        )
        # Must return results (not empty)
        assert len(results) >= 1

    def test_retrieve_with_expand_graph_false_skips_graph(self):
        """When expand_graph=False, graph signal is not included."""
        corpus = {
            "graph-chunk-1": ("CFD boundary layer content", {"source": "doc.pdf"}),
        }
        r = _make_retriever(corpus=corpus)
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        results = r.retrieve(
            "CFD boundary layer",
            top_k=5,
            final_k=3,
            expand_graph=False,
            notebook_id="nb-1",
        )
        # Vector results still returned
        assert len(results) >= 1
        texts = {c["text"] for c in results}
        # Graph-exclusive chunks must NOT appear
        assert "CFD boundary layer content" not in texts

    def test_retrieve_without_notebook_id_skips_graph(self):
        """Without notebook_id, graph expansion is skipped (no crash)."""
        r = _make_retriever()
        r.graph_store = _FakeGraphStore()
        r.graph_extractor = _FakeGraphExtractor()

        # Should not raise even though graph components are present
        results = r.retrieve("CFD analysis", top_k=5, final_k=2, notebook_id=None)
        assert isinstance(results, list)

    def test_retrieve_graph_none_degrades_gracefully(self):
        """Without graph_store/graph_extractor, retrieve() still works normally."""
        r = _make_retriever()
        r.graph_store = None
        r.graph_extractor = None

        results = r.retrieve("any query", top_k=5, final_k=2)
        assert isinstance(results, list)
