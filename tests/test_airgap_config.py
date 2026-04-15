from core.retrieval import embeddings
from core.retrieval.vector_store import VectorStoreAdapter


def test_embedding_manager_uses_local_files_only_in_production(monkeypatch):
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, local_files_only):
            calls.append((model_name, local_files_only))

        def encode(self, texts, normalize_embeddings):
            return []

    monkeypatch.setattr(embeddings, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EMBEDDING_LOCAL_FILES_ONLY", raising=False)

    embeddings.EmbeddingManager(model_name="local-model")

    assert calls == [("local-model", True)]


def test_embedding_manager_allows_build_time_download_by_default(monkeypatch):
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name, local_files_only):
            calls.append((model_name, local_files_only))

    monkeypatch.setattr(embeddings, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.delenv("EMBEDDING_LOCAL_FILES_ONLY", raising=False)

    embeddings.EmbeddingManager(model_name="build-model")

    assert calls == [("build-model", False)]


def test_embedding_manager_wraps_missing_local_model_error(monkeypatch):
    class FakeSentenceTransformer:
        def __init__(self, model_name, local_files_only):
            raise OSError("not found in local cache")

    monkeypatch.setattr(embeddings, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.setenv("ENVIRONMENT", "production")

    try:
        embeddings.EmbeddingManager(model_name="missing-model")
    except RuntimeError as exc:
        assert "missing-model" in str(exc)
        assert "local cache" in str(exc)
        assert "pre_download_models.py" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for missing local model")


def test_vector_store_disables_chroma_telemetry(monkeypatch):
    calls = {}

    class FakeCollection:
        pass

    class FakeClient:
        def __init__(self, path, settings):
            calls["path"] = path
            calls["settings"] = settings

        def get_or_create_collection(self, name):
            calls["collection"] = name
            return FakeCollection()

    monkeypatch.setattr("core.retrieval.vector_store.chromadb.PersistentClient", FakeClient)

    adapter = VectorStoreAdapter(persist_directory="tmp/vector-db")

    assert adapter.collection_name == "doc_knowledge_base"
    assert calls["path"] == "tmp/vector-db"
    assert calls["collection"] == "doc_knowledge_base"
    assert calls["settings"].anonymized_telemetry is False
