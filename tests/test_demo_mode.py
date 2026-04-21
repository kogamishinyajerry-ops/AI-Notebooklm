from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REAL_MODEL_MODULES = (
    "core.models.chat_message",
    "core.models.graph",
    "core.models.note",
    "core.models.notebook",
    "core.models.source",
    "core.models.studio_output",
)


def _load_real_module(name: str):
    if name.startswith("services.ingestion"):
        sys.modules.pop("services", None)
        sys.modules.pop("services.ingestion", None)
    if name == "services.ingestion.parser":
        sys.modules.pop("fitz", None)
        importlib.import_module("fitz")
    if name.startswith("core.storage."):
        sys.modules.pop("core.storage", None)
    if name.startswith("core.models."):
        sys.modules.pop("core.models", None)
    if name.startswith("core.storage."):
        for module_name in _REAL_MODEL_MODULES:
            sys.modules.pop(module_name, None)
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _load_real_fitz():
    sys.modules.pop("fitz", None)
    return importlib.import_module("fitz")


class DemoIngestionService:
    def __init__(self):
        self.vector_store = types.SimpleNamespace(delete=lambda **kwargs: None)

    def process_file(
        self,
        file_path,
        space_id="default",
        source_id=None,
        transaction=None,
    ):
        PDFParser = _load_real_module("services.ingestion.parser").PDFParser

        parser = PDFParser(file_path)
        try:
            page_count = parser.page_count
            chunks = parser.extract_chunks()
        finally:
            parser.close()
        return len(chunks), page_count


class FakeRetrieverEngine:
    def __init__(self, contexts=None):
        self.contexts = contexts or []

    def retrieve(self, *args, **kwargs):
        return self.contexts


@pytest.fixture(autouse=True)
def _cleanup_imported_api_modules():
    yield
    for module_name in (
        "apps.api.main",
        "services",
        "services.ingestion",
        "services.ingestion.service",
        "core.retrieval.retriever",
        "core.governance.gateway",
        "core.governance.prompts",
        "core.models",
        *_REAL_MODEL_MODULES,
    ):
        sys.modules.pop(module_name, None)


def _import_api_main(monkeypatch):
    bootstrap_ingestion = types.ModuleType("services.ingestion.service")

    class _BootstrapIngestionService:
        def __init__(self):
            self.vector_store = types.SimpleNamespace(delete=lambda **kwargs: None)

    bootstrap_ingestion.IngestionService = _BootstrapIngestionService
    monkeypatch.setitem(sys.modules, "services.ingestion.service", bootstrap_ingestion)

    bootstrap_retriever = types.ModuleType("core.retrieval.retriever")
    bootstrap_retriever.RetrieverEngine = FakeRetrieverEngine
    monkeypatch.setitem(sys.modules, "core.retrieval.retriever", bootstrap_retriever)

    sys.modules.pop("services", None)
    sys.modules.pop("services.ingestion", None)
    sys.modules.pop("core.models", None)
    for module_name in _REAL_MODEL_MODULES:
        sys.modules.pop(module_name, None)
    sys.modules.pop("core.storage", None)
    sys.modules.pop("core.governance.gateway", None)
    sys.modules.pop("core.governance.prompts", None)
    monkeypatch.setitem(sys.modules, "fitz", _load_real_fitz())
    sys.modules.pop("apps.api.main", None)
    return importlib.import_module("apps.api.main")


def _install_test_stores(api_main, tmp_path):
    NotebookStore = _load_real_module("core.storage.notebook_store").NotebookStore
    SourceRegistry = _load_real_module("core.storage.source_registry").SourceRegistry
    NoteStore = _load_real_module("core.storage.note_store").NoteStore
    ChatHistoryStore = _load_real_module("core.storage.chat_history_store").ChatHistoryStore
    StudioStore = _load_real_module("core.storage.studio_store").StudioStore
    GraphStore = _load_real_module("core.storage.graph_store").GraphStore
    DailyUploadQuota = _load_real_module("core.governance.quota_store").DailyUploadQuota
    NotebookCountCap = _load_real_module("core.governance.quota_store").NotebookCountCap
    AuditStore = _load_real_module("core.governance.audit_store").AuditStore

    db_path = tmp_path / "notebooks.db"
    spaces_dir = tmp_path / "spaces"
    api_main.notebook_store = NotebookStore(db_path=db_path, spaces_dir=spaces_dir)
    api_main.source_registry = SourceRegistry(db_path=db_path, spaces_dir=spaces_dir)
    api_main.note_store = NoteStore(db_path=db_path, spaces_dir=spaces_dir)
    api_main.chat_history_store = ChatHistoryStore(db_path=db_path, spaces_dir=spaces_dir)
    api_main.studio_store = StudioStore(db_path=db_path, spaces_dir=spaces_dir)
    api_main.graph_store = GraphStore(db_path=db_path, spaces_dir=spaces_dir)
    api_main.upload_quota = DailyUploadQuota(db_path=db_path)
    api_main.notebook_cap = NotebookCountCap(db_path=db_path)
    api_main.audit_store = AuditStore(db_path=db_path)
    api_main.ingestion_service = DemoIngestionService()
    return db_path, spaces_dir


def test_demo_routes_return_404_when_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_DEMO_MODE", raising=False)
    api_main = _import_api_main(monkeypatch)

    client = TestClient(api_main.app)

    assert client.get("/api/v1/demo/status").status_code == 404
    assert client.post("/api/v1/demo/seed").status_code == 404


def test_demo_seed_is_idempotent_and_creates_ready_source(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    api_main = _import_api_main(monkeypatch)

    with TestClient(api_main.app) as client:
        _install_test_stores(api_main, tmp_path)
        api_main.get_llm_settings_snapshot = lambda: {
            "provider": "minimax",
            "configured_url": "https://api.minimaxi.com/anthropic",
            "model_name": "MiniMax-M2.7-highspeed",
            "is_external_validation": True,
        }
        api_main.get_obsidian_vault = lambda: None

        first = client.post("/api/v1/demo/seed")
        second = client.post("/api/v1/demo/seed")

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        first_payload = first.json()
        second_payload = second.json()
        assert first_payload["ready"] is True
        assert first_payload["source"]["status"] == "ready"
        assert first_payload["source"]["chunk_count"] > 0
        assert first_payload["source"]["page_count"] == 5
        assert Path(first_payload["source"]["file_path"]).exists()
        assert first_payload["notebook"]["id"] == second_payload["notebook"]["id"]
        assert first_payload["source"]["id"] == second_payload["source"]["id"]
        assert second_payload["created_source"] is False
        assert "FADEC 发出 Deploy Command 的安全联锁有哪些？" in second_payload["questions"]


def test_demo_seed_repairs_and_deduplicates_existing_broken_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_DEMO_MODE", "1")
    api_main = _import_api_main(monkeypatch)

    with TestClient(api_main.app) as client:
        _install_test_stores(api_main, tmp_path)
        api_main.get_llm_settings_snapshot = lambda: {
            "provider": "minimax",
            "configured_url": "https://api.minimaxi.com/anthropic",
            "model_name": "MiniMax-M2.7-highspeed",
            "is_external_validation": True,
        }
        api_main.get_obsidian_vault = lambda: None

        notebook = api_main.notebook_store.create(api_main.DEMO_NOTEBOOK_NAME)
        broken_a = api_main.source_registry.register(
            notebook.id,
            api_main.DEMO_SOURCE_FILENAME,
            str(tmp_path / "demo-broken-a.pdf"),
        )
        api_main.source_registry.update_status(
            notebook.id,
            broken_a.id,
            "failed",
            page_count=0,
            chunk_count=0,
            error_message="broken",
        )
        broken_b = api_main.source_registry.register(
            notebook.id,
            api_main.DEMO_SOURCE_FILENAME,
            str(tmp_path / "demo-broken-b.pdf"),
        )
        api_main.source_registry.update_status(
            notebook.id,
            broken_b.id,
            "ready",
            page_count=0,
            chunk_count=0,
            error_message="stale",
        )
        api_main.notebook_store.update(notebook.id, source_count=2)

        first = client.post("/api/v1/demo/seed")
        second = client.post("/api/v1/demo/seed")

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        payload = first.json()
        follow_up = second.json()
        assert payload["ready"] is True
        assert payload["source"]["id"] in {broken_a.id, broken_b.id}
        assert payload["source"]["status"] == "ready"
        assert payload["source"]["chunk_count"] > 0
        assert payload["source"]["page_count"] == 5
        assert follow_up["source"]["id"] == payload["source"]["id"]

        demo_sources = api_main.source_registry.list_by_notebook(notebook.id)
        assert len(demo_sources) == 1
        assert demo_sources[0].id == payload["source"]["id"]
        assert demo_sources[0].chunk_count > 0
        assert demo_sources[0].page_count == 5
        assert Path(demo_sources[0].file_path).exists()
        assert api_main.notebook_store.get(notebook.id).source_count == 1


def test_chat_response_includes_evidence_without_changing_citation_gate(monkeypatch, tmp_path):
    monkeypatch.delenv("ENABLE_DEMO_MODE", raising=False)
    api_main = _import_api_main(monkeypatch)

    contexts = [
        {
            "text": "FADEC sends Deploy Command only after TR_WOW equals 1 and locks are unlocked.",
            "metadata": {
                "source": "demo.pdf",
                "page": 4,
                "bbox": [72.0, 120.0, 420.0, 180.0],
            },
        }
    ]

    with TestClient(api_main.app) as client:
        _install_test_stores(api_main, tmp_path)
        api_main.retriever_engine = FakeRetrieverEngine(contexts)
        api_main.invoke_configured_llm = lambda system_prompt, user_query: (
            'FADEC deploy requires TR_WOW and lock confirmation '
            '<citation src="demo.pdf" page="4">TR_WOW equals 1 and locks are unlocked</citation>.'
        )

        notebook = client.post("/api/v1/notebooks", json={"name": "Evidence QA"}).json()
        source = api_main.source_registry.register(
            notebook["id"],
            "demo.pdf",
            str(tmp_path / "demo.pdf"),
        )
        api_main.source_registry.update_status(
            notebook["id"],
            source.id,
            "ready",
            page_count=5,
            chunk_count=1,
        )

        resp = client.post(
            "/api/v1/chat",
            json={
                "notebook_id": notebook["id"],
                "query": "FADEC Deploy Command 的安全联锁有哪些？",
                "save_history": False,
            },
        )

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["is_fully_verified"] is True
        assert payload["citations"][0]["source_file"] == "demo.pdf"
        assert payload["evidence"][0]["source_file"] == "demo.pdf"
        assert payload["evidence"][0]["page_number"] == 4
        assert "FADEC sends Deploy Command" in payload["evidence"][0]["snippet"]
