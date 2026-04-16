"""
test_retriever.py
=================
Basic contract tests for RetrieverEngine.
Updated for S-22: make_retriever sets bm25_index and query_expander.
"""
from core.retrieval.retriever import RetrieverEngine
from core.retrieval.bm25_index import BM25Index
from core.retrieval.query_expander import QueryExpander


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


class FakeReranker:
    def __init__(self):
        self.inputs = None

    def rerank(self, query, chunks, top_n):
        self.inputs = (query, chunks, top_n)
        return chunks[:top_n]


def make_retriever():
    retriever = RetrieverEngine.__new__(RetrieverEngine)
    retriever.embedding_manager = FakeEmbeddingManager()
    retriever.vector_store = FakeVectorStore()
    retriever.reranker = FakeReranker()
    retriever.bm25_index = BM25Index()       # empty — hybrid degrades to vector-only
    retriever.query_expander = QueryExpander()
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
