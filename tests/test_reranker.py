from core.retrieval.reranker import CrossEncoderReranker


class FakeCrossEncoderModel:
    def __init__(self, scores):
        self._scores = scores

    def predict(self, pairs, batch_size=32, show_progress_bar=False, convert_to_numpy=True):
        return self._scores


def test_reranker_sorts_by_cross_encoder_score(monkeypatch):
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(
        reranker,
        "_get_model",
        lambda: FakeCrossEncoderModel([0.1, 0.9, 0.4]),
    )

    chunks = [
        {"text": "A", "metadata": {"source": "a.pdf", "page": "1"}},
        {"text": "B", "metadata": {"source": "b.pdf", "page": "2"}},
        {"text": "C", "metadata": {"source": "c.pdf", "page": "3"}},
    ]

    ranked = reranker.rerank("query", chunks, top_n=2)

    assert [chunk["text"] for chunk in ranked] == ["B", "C"]
    assert ranked[0]["metadata"]["_rerank_score"] == 0.9


def test_reranker_falls_back_to_input_order_when_model_unavailable(monkeypatch):
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(reranker, "_get_model", lambda: None)

    chunks = [
        {"text": "A", "metadata": {"source": "a.pdf", "page": "1"}},
        {"text": "B", "metadata": {"source": "b.pdf", "page": "2"}},
    ]

    ranked = reranker.rerank("query", chunks, top_n=1)

    assert [chunk["text"] for chunk in ranked] == ["A"]
