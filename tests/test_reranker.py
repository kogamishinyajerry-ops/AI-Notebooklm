from __future__ import annotations

import importlib
import sys
import types


def _load_reranker_module(monkeypatch, sentence_transformers_module):
    monkeypatch.setitem(sys.modules, "sentence_transformers", sentence_transformers_module)
    sys.modules.pop("core.retrieval.reranker", None)
    import core.retrieval.reranker as reranker
    return importlib.reload(reranker)


def test_reranker_uses_local_files_only_in_production(monkeypatch):
    calls = []

    fake_module = types.ModuleType("sentence_transformers")

    class FakeCrossEncoder:
        def __init__(self, model_name, local_files_only=False, **kwargs):
            calls.append((model_name, local_files_only))

        def predict(self, pairs):
            return [0.0 for _ in pairs]

    fake_module.CrossEncoder = FakeCrossEncoder
    fake_module.SentenceTransformer = object
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RERANKER_LOCAL_FILES_ONLY", raising=False)

    reranker = _load_reranker_module(monkeypatch, fake_module)
    model = reranker.CrossEncoderReranker(model_name="reranker-model")
    model.rerank("query", [{"text": "doc"}], top_n=1)

    assert calls == [("reranker-model", True)]


def test_reranker_orders_chunks_by_predicted_score(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")

    class FakeCrossEncoder:
        def __init__(self, model_name, local_files_only=False, **kwargs):
            self.model_name = model_name

        def predict(self, pairs):
            return [0.1, 0.9, 0.4]

    fake_module.CrossEncoder = FakeCrossEncoder
    fake_module.SentenceTransformer = object
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RERANKER_LOCAL_FILES_ONLY", raising=False)

    reranker = _load_reranker_module(monkeypatch, fake_module)
    model = reranker.CrossEncoderReranker()
    chunks = [{"text": "a"}, {"text": "b"}, {"text": "c"}]

    result = model.rerank("query", chunks, top_n=2)

    assert [item["text"] for item in result] == ["b", "c"]
    assert result[0]["reranker_score"] == 0.9
    assert result[1]["reranker_score"] == 0.4


def test_reranker_falls_back_when_model_is_unavailable(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = object

    monkeypatch.setenv("ENVIRONMENT", "production")
    reranker = _load_reranker_module(monkeypatch, fake_module)
    model = reranker.CrossEncoderReranker()
    chunks = [{"text": "first"}, {"text": "second"}]

    result = model.rerank("query", chunks, top_n=2)

    assert result == chunks


def test_reranker_falls_back_when_prediction_errors(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")

    class FakeCrossEncoder:
        def __init__(self, model_name, local_files_only=False, **kwargs):
            pass

        def predict(self, pairs):
            raise RuntimeError("predict failed")

    fake_module.CrossEncoder = FakeCrossEncoder
    fake_module.SentenceTransformer = object

    reranker = _load_reranker_module(monkeypatch, fake_module)
    model = reranker.CrossEncoderReranker()
    chunks = [{"text": "first"}, {"text": "second"}]

    result = model.rerank("query", chunks, top_n=1)

    assert result == [chunks[0]]
