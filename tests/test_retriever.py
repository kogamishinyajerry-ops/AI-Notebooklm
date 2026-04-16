"""
test_retriever.py
=================
Basic contract tests for RetrieverEngine.
Updated for S-22: make_retriever sets bm25_index and query_expander.
Updated for S-23: stubs installed at module level so file can run standalone.
"""
import sys
import types
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stubs — must be installed before any core.retrieval imports
# ---------------------------------------------------------------------------

def _stub(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


for _name in ("sentence_transformers", "chromadb", "fitz", "transformers", "torch",
              "tenacity"):
    if _name not in sys.modules:
        s = _stub(_name)
        if _name == "chromadb":
            cfg = _stub("chromadb.config")
            cfg.Settings = dict
            s.PersistentClient = MagicMock
            s.config = cfg

for _name in ("core.retrieval.embeddings", "core.retrieval.reranker",
              "core.retrieval.vector_store"):
    if _name not in sys.modules:
        mod = _stub(_name)
        mod.EmbeddingManager = MagicMock
        mod.CrossEncoderReranker = MagicMock
        mod.VectorStoreAdapter = MagicMock

# ---------------------------------------------------------------------------

from core.retrieval.retriever import RetrieverEngine


class FakeEmbedding:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeEmbeddingManager:
    def encode(self, texts):
        return [FakeEmbedding([0.1, 0.2, 0.3]) for _ in texts]


class FakeVectorStore:
    def __init__(self):
        self.query_embeddings = None
        self.top_k = None
        self.where = None

    def query(self, query_embeddings, top_k, where=None):
        self.query_embeddings = query_embeddings
        self.top_k = top_k
        self.where = where
        return {
            "documents": [["doc a", "doc b"]],
            "metadatas": [[
                {"source": "a.pdf", "page": "1"},
                {"source": "b.pdf", "page": "2"},
            ]],
        }

    def get_by_ids(self, ids: list) -> dict:
        return {"documents": [], "metadatas": []}


class FakeReranker:
    def __init__(self):
        self.inputs = None

    def rerank(self, query, chunks, top_n):
        self.inputs = (query, chunks, top_n)
        return chunks[:top_n]


class _FakeBM25Index:
    size = 0
    def build(self, corpus): pass
    def query(self, q, top_k=10, extra_tokens=None): return []


class _FakeQueryExpander:
    def expand(self, query): return query, []


def make_retriever():
    retriever = RetrieverEngine.__new__(RetrieverEngine)
    retriever.embedding_manager = FakeEmbeddingManager()
    retriever.vector_store = FakeVectorStore()
    retriever.reranker = FakeReranker()
    retriever.bm25_index = _FakeBM25Index()    # empty — hybrid degrades to vector-only
    retriever.query_expander = _FakeQueryExpander()
    return retriever


def test_retriever_uses_vector_store_query_contract():
    """Vector store receives the embedded query and top_k."""
    retriever = make_retriever()

    results = retriever.retrieve("test query", top_k=7, final_k=1)

    # Query embedding passed through unchanged
    assert retriever.vector_store.query_embeddings == [0.1, 0.2, 0.3]
    assert retriever.vector_store.top_k == 7
    # Final result is final_k=1
    assert len(results) == 1
    assert results[0]["text"] == "doc a"


def test_retriever_returns_empty_when_vector_store_has_no_documents():
    retriever = make_retriever()
    retriever.vector_store.query = lambda query_embeddings, top_k, where=None: {"documents": [[]], "metadatas": [[]]}

    assert retriever.retrieve("test query") == []
