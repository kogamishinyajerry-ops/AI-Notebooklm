from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    if "services.ingestion.service" not in sys.modules:
        _stub("services.ingestion")
        svc_mod = _stub("services.ingestion.service")

        class _FakeIngestionService:
            def __init__(self):
                self.vector_store = MagicMock()

            def process_file(self, *args, **kwargs):
                return 0, 0

        svc_mod.IngestionService = _FakeIngestionService

    if "services.ingestion.filenames" not in sys.modules:
        fn_mod = _stub("services.ingestion.filenames")
        fn_mod.safe_upload_path = MagicMock()
        fn_mod.validate_pdf_magic = MagicMock()

    if "core.ingestion.transaction" not in sys.modules:
        tx_mod = _stub("core.ingestion.transaction")
        tx_mod.IngestTransaction = MagicMock
        tx_mod.cleanup_committed_transactions = MagicMock()
        tx_mod.iter_space_ids = MagicMock(return_value=[])
        tx_mod.recover_incomplete_transactions = MagicMock()
        tx_mod.summarize_transaction_health = MagicMock(return_value={})

    if "core.retrieval.retriever" not in sys.modules:
        retr_mod = _stub("core.retrieval.retriever")

        class _FakeRetrieverEngine:
            def __init__(self):
                self.graph_store = None
                self.graph_extractor = None

            def retrieve(self, *args, **kwargs):
                return [
                    {
                        "text": "chunk",
                        "metadata": {"source": "doc.pdf", "page": "1", "source_id": "src-1"},
                    }
                ]

        retr_mod.RetrieverEngine = _FakeRetrieverEngine

    if "core.governance.prompts" not in sys.modules:
        prompts_mod = _stub("core.governance.prompts")
        prompts_mod.QA_SYSTEM_PROMPT = "{context_blocks}"
        prompts_mod.build_context_block = lambda ctxs: str(ctxs)
        prompts_mod.STUDIO_PROMPTS = {
            key: "{context_blocks}"
            for key in ("summary", "faq", "briefing", "glossary", "action_items")
        }

    if "core.governance.gateway" not in sys.modules:
        gateway_mod = _stub("core.governance.gateway")

        class _Gateway:
            @staticmethod
            def validate_and_parse(raw_response, contexts):
                return True, "safe response", []

        gateway_mod.AntiHallucinationGateway = _Gateway

    if "core.models.source" not in sys.modules:
        src_mod = _stub("core.models.source")

        class _SourceStatus:
            UPLOADING = "UPLOADING"
            PROCESSING = "PROCESSING"
            READY = "READY"
            FAILED = "FAILED"

        src_mod.SourceStatus = _SourceStatus

    for name in (
        "core.storage.notebook_store",
        "core.storage.source_registry",
        "core.storage.note_store",
        "core.storage.chat_history_store",
        "core.storage.studio_store",
        "core.storage.graph_store",
        "core.knowledge.graph_extractor",
    ):
        if name not in sys.modules:
            mod = _stub(name)
            mod_name = name.rsplit(".", 1)[-1]
            class_name = "".join(part.capitalize() for part in mod_name.split("_"))
            setattr(mod, class_name, MagicMock)

    if "core.models.studio_output" not in sys.modules:
        so_mod = _stub("core.models.studio_output")

        class _StudioOutputType:
            @staticmethod
            def values():
                return ["summary", "faq", "briefing", "glossary", "action_items"]

        so_mod.StudioOutputType = _StudioOutputType


@pytest.fixture(autouse=True)
def _cleanup_stubbed_modules():
    yield
    for mod in (
        "apps.api.main",
        "core.retrieval.retriever",
    ):
        sys.modules.pop(mod, None)


@dataclass
class _Notebook:
    id: str
    name: str
    owner_id: str | None = None
    source_count: int = 0

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "source_count": self.source_count,
        }


@dataclass
class _Source:
    id: str


class _FakeNotebookStore:
    def __init__(self, notebooks: List[_Notebook]):
        self._notebooks: Dict[str, _Notebook] = {notebook.id: notebook for notebook in notebooks}
        self.created: List[_Notebook] = []

    def create(self, name: str, owner_id: str | None = None):
        notebook = _Notebook(id=f"nb-{len(self._notebooks) + 1}", name=name, owner_id=owner_id)
        self._notebooks[notebook.id] = notebook
        self.created.append(notebook)
        return notebook

    def get(self, notebook_id: str):
        return self._notebooks.get(notebook_id)

    def list_all(self):
        return list(self._notebooks.values())

    def delete(self, notebook_id: str):
        return self._notebooks.pop(notebook_id, None) is not None


def _import_api():
    _install_stubs()
    sys.modules.pop("apps.api.main", None)
    import apps.api.main  # noqa: PLC0415

    return sys.modules["apps.api.main"]


def _build_client(monkeypatch, notebooks: List[_Notebook], notebook_sources: Dict[str, List[str]] | None = None):
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    api_main = _import_api()

    notebook_store = _FakeNotebookStore(notebooks)
    source_registry = MagicMock()
    source_registry.spaces_dir = MagicMock()
    source_registry.list_by_notebook.side_effect = lambda nid: [
        _Source(id=source_id) for source_id in (notebook_sources or {}).get(nid, [])
    ]
    source_registry.get.return_value = None

    retriever_engine = MagicMock()
    retriever_engine.retrieve.return_value = [
        {
            "text": "chunk",
            "metadata": {"source": "doc.pdf", "page": "1", "source_id": "src-1"},
        }
    ]

    api_main.notebook_store = notebook_store
    api_main.source_registry = source_registry
    api_main.retriever_engine = retriever_engine
    api_main.invoke_local_llm = MagicMock(
        return_value="<citation src='doc.pdf' page='1'>答案内容</citation>"
    )

    return TestClient(api_main.app), notebook_store, retriever_engine


def test_requires_api_key_when_auth_enabled(monkeypatch):
    client, _, _ = _build_client(monkeypatch, notebooks=[])

    resp = client.get("/api/v1/notebooks")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "API key required"


def test_create_notebook_assigns_owner_from_api_key(monkeypatch):
    client, notebook_store, _ = _build_client(monkeypatch, notebooks=[])

    resp = client.post(
        "/api/v1/notebooks",
        headers={"X-API-Key": "key-alice"},
        json={"name": "Flight Controls"},
    )

    assert resp.status_code == 201
    assert resp.json()["owner_id"] == "alice"
    assert notebook_store.created[0].owner_id == "alice"


def test_list_notebooks_filters_to_current_owner(monkeypatch):
    client, _, _ = _build_client(
        monkeypatch,
        notebooks=[
            _Notebook(id="nb-a", name="Alice Notebook", owner_id="alice"),
            _Notebook(id="nb-b", name="Bob Notebook", owner_id="bob"),
        ],
    )

    resp = client.get("/api/v1/notebooks", headers={"Authorization": "Bearer key-alice"})

    assert resp.status_code == 200
    payload = resp.json()
    assert [item["id"] for item in payload] == ["nb-a"]


def test_chat_rejects_access_to_foreign_notebook(monkeypatch):
    client, _, retriever_engine = _build_client(
        monkeypatch,
        notebooks=[_Notebook(id="nb-b", name="Bob Notebook", owner_id="bob")],
        notebook_sources={"nb-b": ["src-1"]},
    )

    resp = client.post(
        "/api/v1/chat",
        headers={"X-API-Key": "key-alice"},
        json={"query": "test", "notebook_id": "nb-b"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Notebook access denied"
    retriever_engine.retrieve.assert_not_called()
