from __future__ import annotations

import sys
import types
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
        # graph_store.py imports these at module level; add them so deferred imports succeed
        from pathlib import Path
        tx_mod.DEFAULT_SPACES_DIR = Path("data/spaces")
        tx_mod.utc_now_iso = lambda: "2025-01-01T00:00:00Z"

    if "core.retrieval.retriever" not in sys.modules:
        retr_mod = _stub("core.retrieval.retriever")

        class _FakeRetrieverEngine:
            def __init__(self):
                self.graph_store = None
                self.graph_extractor = None

            def retrieve(self, *args, **kwargs):
                return []

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
        # Evict the bare core.storage stub (created by test_cross_notebook_isolation).
        # Without this, core.storage remains as a regular ModuleType that replaces
        # the namespace package, causing "core.storage is not a package" in later tests.
        "core.storage",
        # Storage stubs installed by _install_stubs() — must be evicted so
        # subsequent tests (e.g. test_graph.py) get the real storage modules.
        "core.storage.notebook_store",
        "core.storage.source_registry",
        "core.storage.note_store",
        "core.storage.chat_history_store",
        "core.storage.studio_store",
        "core.storage.graph_store",
        "core.storage.sqlite_db",
        "core.knowledge.graph_extractor",
        # Also evict core.ingestion.transaction stub so graph_store.py can import it
        "core.ingestion.transaction",
    ):
        sys.modules.pop(mod, None)


def _import_api():
    _install_stubs()
    sys.modules.pop("apps.api.main", None)
    import apps.api.main  # noqa: PLC0415

    return sys.modules["apps.api.main"]


def test_llm_health_endpoint_returns_probe_payload():
    api_main = _import_api()
    api_main.probe_local_llm = MagicMock(
        return_value={
            "status": "ok",
            "provider": "local",
            "available": True,
            "reachable": True,
            "configured_url": "http://localhost:8001/v1",
            "models": ["qwen-2.5"],
        }
    )

    client = TestClient(api_main.app)
    resp = client.get("/api/v1/llm/health")

    assert resp.status_code == 200
    assert resp.json()["reachable"] is True
    assert resp.json()["configured_url"] == "http://localhost:8001/v1"
    assert resp.json()["provider"] == "local"


def test_llm_health_endpoint_returns_structured_503_for_misconfiguration():
    api_main = _import_api()
    api_main.get_llm_settings_snapshot = MagicMock(
        return_value={
            "provider": "minimax",
            "configured_url": "https://api.minimax.io/v1",
            "model_name": "MiniMax-M2.7-highspeed",
            "is_external_validation": True,
        }
    )
    api_main.probe_local_llm = MagicMock(
        side_effect=api_main.LLMConfigurationError("MINIMAX_API_KEY is required when LLM_PROVIDER=minimax.")
    )

    client = TestClient(api_main.app, raise_server_exceptions=False)
    resp = client.get("/api/v1/llm/health")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["status"] == "misconfigured"
    assert payload["provider"] == "minimax"
    assert payload["is_external_validation"] is True
    assert "MINIMAX_API_KEY" in payload["unavailable_reason"]


def test_llm_health_endpoint_returns_200_when_provider_unreachable():
    api_main = _import_api()
    api_main.probe_local_llm = MagicMock(
        return_value={
            "status": "unreachable",
            "provider": "local",
            "available": False,
            "reachable": False,
            "configured_url": "http://localhost:8001/v1",
            "unavailable_reason": "connection refused",
        }
    )

    client = TestClient(api_main.app)
    resp = client.get("/api/v1/llm/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "unreachable"
    assert resp.json()["available"] is False


def test_llm_health_endpoint_uses_external_timeout_for_minimax():
    api_main = _import_api()
    api_main.get_llm_settings_snapshot = MagicMock(
        return_value={
            "provider": "minimax",
            "configured_url": "https://api.minimaxi.com/anthropic",
            "model_name": "MiniMax-M2.7-highspeed",
            "is_external_validation": True,
        }
    )
    api_main.probe_local_llm = MagicMock(
        return_value={
            "status": "ok",
            "provider": "minimax",
            "available": True,
            "reachable": True,
            "configured_url": "https://api.minimaxi.com/anthropic",
        }
    )

    client = TestClient(api_main.app)
    resp = client.get("/api/v1/llm/health")

    assert resp.status_code == 200
    assert resp.json()["provider"] == "minimax"
    api_main.probe_local_llm.assert_called_once_with(timeout=20.0)
