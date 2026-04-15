from core.retrieval.retriever import RetrieverEngine


class FakeEmbedding:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeEmbeddingManager:
    def encode(self, texts):
        assert texts == ["test query"]
        return [FakeEmbedding([0.1, 0.2, 0.3])]


class FakeVectorStore:
    def __init__(self):
        self.query_embeddings = None
        self.top_k = None

    def query(self, query_embeddings, top_k):
        self.query_embeddings = query_embeddings
        self.top_k = top_k
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
    return retriever


def test_retriever_uses_vector_store_query_contract():
    retriever = make_retriever()

    results = retriever.retrieve("test query", top_k=7, final_k=1)

    assert retriever.vector_store.query_embeddings == [0.1, 0.2, 0.3]
    assert retriever.vector_store.top_k == 7
    assert retriever.reranker.inputs == (
        "test query",
        [
            {"text": "doc a", "metadata": {"source": "a.pdf", "page": "1"}},
            {"text": "doc b", "metadata": {"source": "b.pdf", "page": "2"}},
        ],
        1,
    )
    assert results == [{"text": "doc a", "metadata": {"source": "a.pdf", "page": "1"}}]


def test_retriever_returns_empty_when_vector_store_has_no_documents():
    retriever = make_retriever()
    retriever.vector_store.query = lambda query_embeddings, top_k: {"documents": [[]], "metadatas": [[]]}

    assert retriever.retrieve("test query") == []
