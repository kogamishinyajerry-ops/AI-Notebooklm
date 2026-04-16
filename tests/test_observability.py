from __future__ import annotations

import json
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
                return True, "safe response", [
                    {
                        "source_file": "doc.pdf",
                        "page_number": 1,
                        "content": "chunk",
                        "bbox": None,
                    }
                ]

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

    def to_dict(self):
        return {"id": self.id, "name": self.name, "owner_id": self.owner_id}


@dataclass
class _Source:
    id: str


class _FakeNotebookStore:
    def __init__(self, notebooks: List[_Notebook]):
        self._notebooks: Dict[str, _Notebook] = {notebook.id: notebook for notebook in notebooks}

    def get(self, notebook_id: str):
        return self._notebooks.get(notebook_id)

    def list_all(self):
        return list(self._notebooks.values())


def _import_api():
    _install_stubs()
    sys.modules.pop("apps.api.main", None)
    import apps.api.main  # noqa: PLC0415

    return sys.modules["apps.api.main"]


def _build_client(monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    api_main = _import_api()

    notebook_store = _FakeNotebookStore([_Notebook(id="nb-1", name="Notebook 1")])
    source_registry = MagicMock()
    source_registry.spaces_dir = MagicMock()
    source_registry.list_by_notebook.side_effect = lambda nid: [_Source(id="src-1")]

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
    api_main.AntiHallucinationGateway = type(
        "_Gateway",
        (),
        {
            "validate_and_parse": staticmethod(
                lambda raw_response, contexts: (
                    True,
                    "safe response",
                    [
                        {
                            "source_file": "doc.pdf",
                            "page_number": 1,
                            "content": "chunk",
                            "bbox": None,
                        }
                    ],
                )
            )
        },
    )

    return TestClient(api_main.app)


def _extract_events(caplog):
    events = []
    for record in caplog.records:
        if record.name != "comac.api":
            continue
        events.append(json.loads(record.message))
    return events


def test_request_logging_adds_request_id(monkeypatch, caplog):
    caplog.set_level("INFO", logger="comac.api")
    client = _build_client(monkeypatch)

    resp = client.get("/health", headers={"X-Request-ID": "req-123"})

    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "req-123"

    events = _extract_events(caplog)
    http_event = next(event for event in events if event["event"] == "http.request")
    assert http_event["request_id"] == "req-123"
    assert http_event["path"] == "/health"
    assert http_event["status_code"] == 200


def test_chat_logs_retrieval_summary(monkeypatch, caplog):
    caplog.set_level("INFO", logger="comac.api")
    client = _build_client(monkeypatch)

    resp = client.post(
        "/api/v1/chat",
        headers={"X-Request-ID": "req-chat"},
        json={"query": "test", "notebook_id": "nb-1", "save_history": False},
    )

    assert resp.status_code == 200
    events = _extract_events(caplog)
    retrieval_event = next(event for event in events if event["event"] == "retrieval.summary")

    assert retrieval_event["request_id"] == "req-chat"
    assert retrieval_event["notebook_id"] == "nb-1"
    assert retrieval_event["source_scope_size"] == 1
    assert retrieval_event["contexts_returned"] == 1
    assert retrieval_event["citations_returned"] == 1
    assert retrieval_event["is_fully_verified"] is True
    assert retrieval_event["llm_available"] is True
