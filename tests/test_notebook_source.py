import importlib
import sys
import types

from fastapi.testclient import TestClient

from core.models.source import SourceStatus
from core.storage.notebook_store import NotebookStore
from core.storage.source_registry import SourceRegistry


def test_create_list_and_delete_notebook(tmp_path):
    store = NotebookStore(db_path=tmp_path / "notebooks.db", spaces_dir=tmp_path / "spaces")

    first = store.create("First notebook")
    second = store.create("Second notebook")

    assert [notebook.name for notebook in store.list_all()] == ["First notebook", "Second notebook"]
    assert (tmp_path / "spaces" / first.id).exists()

    assert store.delete(first.id) is True
    assert store.delete("missing") is False
    assert [notebook.id for notebook in store.list_all()] == [second.id]
    assert not (tmp_path / "spaces" / first.id).exists()


def test_source_registry_lifecycle_and_notebook_isolation(tmp_path):
    registry = SourceRegistry(db_path=tmp_path / "notebooks.db", spaces_dir=tmp_path / "spaces")

    source_a = registry.register("notebook-a", "a.pdf", "data/spaces/notebook-a/docs/a.pdf")
    source_b = registry.register("notebook-b", "b.pdf", "data/spaces/notebook-b/docs/b.pdf")

    ready = registry.update_status(
        "notebook-a",
        source_a.id,
        SourceStatus.READY,
        page_count=2,
        chunk_count=10,
    )

    assert ready.status == SourceStatus.READY
    assert ready.page_count == 2
    assert ready.chunk_count == 10
    assert [source.id for source in registry.list_by_notebook("notebook-a")] == [source_a.id]
    assert [source.id for source in registry.list_by_notebook("notebook-b")] == [source_b.id]

    assert registry.delete("notebook-a", source_a.id) is True
    assert registry.list_by_notebook("notebook-a") == []


class FakeCollection:
    def add(self, **kwargs):
        pass

    def delete(self, **kwargs):
        pass

    def query(self, **kwargs):
        return {"documents": [[]], "metadatas": [[]]}


class FakeClient:
    def __init__(self, path, settings):
        self.path = path
        self.settings = settings

    def get_or_create_collection(self, name):
        return FakeCollection()


class FakeSentenceTransformer:
    def __init__(self, model_name, local_files_only):
        self.model_name = model_name
        self.local_files_only = local_files_only


class FakeVectorStore:
    def __init__(self):
        self.deleted = []

    def delete(self, ids=None, where=None):
        self.deleted.append({"ids": ids, "where": where})


class FakeIngestionService:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.vector_store = FakeVectorStore()
        self.calls = []

    def process_file(self, file_path, space_id="default", source_id=None, transaction=None):
        self.calls.append({
            "file_path": file_path,
            "space_id": space_id,
            "source_id": source_id,
        })
        if self.should_fail:
            raise RuntimeError("parser failed")
        return 4, 2


def import_api_with_fakes(monkeypatch, tmp_path, should_fail=False):
    monkeypatch.setitem(sys.modules, "fitz", types.SimpleNamespace(open=lambda file_path: None))

    fake_sentence_transformers = types.ModuleType("sentence_transformers")
    fake_sentence_transformers.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_sentence_transformers)

    fake_chromadb = types.ModuleType("chromadb")
    fake_chromadb_config = types.ModuleType("chromadb.config")
    fake_chromadb_config.Settings = dict
    fake_chromadb.PersistentClient = FakeClient
    fake_chromadb.config = fake_chromadb_config
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.config", fake_chromadb_config)

    for name in (
        "services.ingestion.parser",
        "services.ingestion.chunker",
        "services.ingestion.filenames",
        "services.ingestion.service",
        "services.ingestion",
        "services",
        "core.models.source",
        "core.models.note",
        "core.models.chat_message",
        "core.models.studio_output",
        "core.models.graph",
        "core.models",
        "core.storage.notebook_store",
        "core.storage.source_registry",
        "core.storage.note_store",
        "core.storage.chat_history_store",
        "core.storage.studio_store",
        "core.storage.graph_store",
        "core.storage",
        "core.knowledge.graph_extractor",
        "core.knowledge",
        "core.ingestion.transaction",
        "core.retrieval.embeddings",
        "core.retrieval.vector_store",
        "core.retrieval.retriever",
        "core.retrieval.bm25_index",
        "core.retrieval.query_expander",
        "apps.api.main",
    ):
        sys.modules.pop(name, None)
    import core.retrieval.embeddings as embeddings

    monkeypatch.setattr(embeddings, "SentenceTransformer", FakeSentenceTransformer)
    api = importlib.import_module("apps.api.main")
    api.notebook_store = NotebookStore(
        db_path=tmp_path / "notebooks.db",
        spaces_dir=tmp_path / "spaces",
    )
    api.source_registry = SourceRegistry(
        db_path=tmp_path / "notebooks.db",
        spaces_dir=tmp_path / "spaces",
    )
    api.ingestion_service = FakeIngestionService(should_fail=should_fail)
    return api


def test_notebook_api_and_upload_creates_ready_source(monkeypatch, tmp_path):
    api = import_api_with_fakes(monkeypatch, tmp_path)
    client = TestClient(api.app)

    created = client.post("/api/v1/notebooks", json={"name": "Flight Laws"}).json()
    upload = client.post(
        f"/api/v1/notebooks/{created['id']}/sources/upload",
        files={"file": ("manual.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    )

    assert upload.status_code == 200
    source = upload.json()["source"]
    assert source["filename"] == "manual.pdf"
    assert source["status"] == "ready"
    assert source["page_count"] == 2
    assert source["chunk_count"] == 4
    assert api.ingestion_service.calls[0]["space_id"] == created["id"]
    assert api.ingestion_service.calls[0]["source_id"] == source["id"]

    listed = client.get(f"/api/v1/notebooks/{created['id']}/sources").json()
    assert [item["id"] for item in listed] == [source["id"]]
    assert client.get(f"/api/v1/notebooks/{created['id']}").json()["source_count"] == 1


def test_delete_source_removes_registry_file_and_vectors(monkeypatch, tmp_path):
    api = import_api_with_fakes(monkeypatch, tmp_path)
    client = TestClient(api.app)
    notebook = client.post("/api/v1/notebooks", json={"name": "Delete Source"}).json()
    source = client.post(
        f"/api/v1/notebooks/{notebook['id']}/sources/upload",
        files={"file": ("manual.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    ).json()["source"]

    response = client.delete(f"/api/v1/notebooks/{notebook['id']}/sources/{source['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/notebooks/{notebook['id']}/sources").json() == []
    assert client.get(f"/api/v1/notebooks/{notebook['id']}").json()["source_count"] == 0
    assert api.ingestion_service.vector_store.deleted == [{"ids": None, "where": {"source_id": source["id"]}}]


def test_delete_notebook_removes_space_and_source_vectors(monkeypatch, tmp_path):
    api = import_api_with_fakes(monkeypatch, tmp_path)
    client = TestClient(api.app)
    notebook = client.post("/api/v1/notebooks", json={"name": "Delete Notebook"}).json()
    first = client.post(
        f"/api/v1/notebooks/{notebook['id']}/sources/upload",
        files={"file": ("first.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    ).json()["source"]
    second = client.post(
        f"/api/v1/notebooks/{notebook['id']}/sources/upload",
        files={"file": ("second.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    ).json()["source"]

    response = client.delete(f"/api/v1/notebooks/{notebook['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/notebooks/{notebook['id']}").status_code == 404
    assert not (tmp_path / "spaces" / notebook["id"]).exists()
    assert api.ingestion_service.vector_store.deleted == [
        {"ids": None, "where": {"source_id": first["id"]}},
        {"ids": None, "where": {"source_id": second["id"]}},
    ]


def test_upload_failure_marks_source_failed(monkeypatch, tmp_path):
    api = import_api_with_fakes(monkeypatch, tmp_path, should_fail=True)
    client = TestClient(api.app)
    notebook = client.post("/api/v1/notebooks", json={"name": "Failure Case"}).json()

    response = client.post(
        f"/api/v1/notebooks/{notebook['id']}/sources/upload",
        files={"file": ("manual.pdf", b"%PDF-1.7\ncontent", "application/pdf")},
    )

    assert response.status_code == 500
    sources = client.get(f"/api/v1/notebooks/{notebook['id']}/sources").json()
    assert len(sources) == 1
    assert sources[0]["status"] == "failed"
    assert sources[0]["error_message"] == "parser failed"
