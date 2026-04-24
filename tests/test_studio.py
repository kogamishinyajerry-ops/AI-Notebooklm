"""
test_studio.py
===============
Tests for S-21: Text Studio Outputs

  * StudioStore: create, list, get, delete
  * StudioOutputType: validation helpers
  * API: GET/POST/DELETE /studio, POST /studio/{id}/save-as-note
  * generate endpoint: 404 unknown notebook, 422 bad type, 422 no sources, 503 LLM down
"""
from __future__ import annotations

import base64
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared stub helpers (same pattern as other test files)
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _patch_transaction():
    name = "core.ingestion.transaction"
    mod = sys.modules.get(name)
    if mod is None:
        mod = _stub(name)
    mod.DEFAULT_SPACES_DIR = "data/spaces"
    mod.resolve_space_path = lambda nb, fn, base_dir=None: \
        Path(str(base_dir or "data/spaces")) / nb / fn
    mod.utc_now_iso = lambda: "2026-04-16T00:00:00Z"
    mod.IngestTransaction = MagicMock
    mod.cleanup_committed_transactions = MagicMock()
    mod.iter_space_ids = MagicMock(return_value=[])
    mod.recover_incomplete_transactions = MagicMock()
    mod.summarize_transaction_health = MagicMock(return_value={})


def _seed_notebooks(db_path: Path, notebook_ids: tuple[str, ...]) -> None:
    from core.storage.sqlite_db import get_connection, init_schema

    conn = get_connection(db_path)
    init_schema(conn)
    try:
        for notebook_id in notebook_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO notebooks
                    (id, name, created_at, updated_at, source_count, owner_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    notebook_id,
                    f"Notebook {notebook_id}",
                    "2026-04-16T00:00:00Z",
                    "2026-04-16T00:00:00Z",
                    0,
                    None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


_REAL_MODULES = (
    "core.storage.studio_store", "core.storage.note_store",
    "core.storage.chat_history_store",
    "core.models.studio_output", "core.models.note", "core.models.chat_message",
    "core.governance.prompts", "core.retrieval.retriever",
)
_PARENT_PACKAGES = ("core.storage", "core.models")


@pytest.fixture(autouse=True)
def _evict_stubs(tmp_path):
    for name in _REAL_MODULES + _PARENT_PACKAGES:
        sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)
    _patch_transaction()
    _seed_notebooks(tmp_path / "notebooks.db", ("nb-1", "nb-a", "nb-b"))
    yield
    for name in _REAL_MODULES + _PARENT_PACKAGES:
        sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)


# ---------------------------------------------------------------------------
# Unit tests: StudioOutputType
# ---------------------------------------------------------------------------

class TestStudioOutputType:
    def test_values_contains_all_types(self):
        from core.models.studio_output import StudioOutputType
        vals = StudioOutputType.values()
        for t in ("summary", "faq", "briefing", "glossary", "action_items", "podcast", "infographic"):
            assert t in vals

    def test_labels_returns_dict(self):
        from core.models.studio_output import StudioOutputType
        labels = StudioOutputType.labels()
        assert "summary" in {k.value for k in labels}

    def test_from_dict_roundtrip(self):
        from core.models.studio_output import StudioOutput
        data = {
            "id": "abc", "notebook_id": "nb-1", "output_type": "summary",
            "title": "摘要 · 00:00", "content": "test content",
            "citations": [], "created_at": "2026-04-16T00:00:00Z",
        }
        out = StudioOutput.from_dict(data)
        assert out.id == "abc"
        assert out.to_dict() == data


# ---------------------------------------------------------------------------
# Unit tests: StudioStore
# ---------------------------------------------------------------------------

class TestStudioStore:
    def test_create_and_list(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "summary", "Generated content", citations=[])
        items = store.list_by_notebook("nb-1")
        assert len(items) == 1
        assert items[0].id == out.id
        assert items[0].output_type == "summary"

    def test_auto_title(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "faq", "Q&A content", citations=[])
        assert "FAQ" in out.title or "faq" in out.title.lower()

    def test_custom_title(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "briefing", "content", citations=[], title="Custom Title")
        assert out.title == "Custom Title"

    def test_get(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "glossary", "Terms...", citations=[])
        fetched = store.get("nb-1", out.id)
        assert fetched is not None
        assert fetched.id == out.id

    def test_get_missing_returns_none(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        assert store.get("nb-1", "ghost") is None

    def test_delete(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "action_items", "Tasks...", citations=[])
        assert store.delete("nb-1", out.id) is True
        assert store.get("nb-1", out.id) is None

    def test_delete_missing_returns_false(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        assert store.delete("nb-1", "ghost") is False

    def test_notebooks_isolated(self, tmp_path):
        from core.storage.studio_store import StudioStore
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        store.create("nb-a", "summary", "A content", citations=[])
        store.create("nb-b", "faq", "B content", citations=[])
        assert len(store.list_by_notebook("nb-a")) == 1
        assert len(store.list_by_notebook("nb-b")) == 1

    def test_citations_persisted(self, tmp_path):
        from core.storage.studio_store import StudioStore
        citations = [{"source_file": "doc.pdf", "page_number": 2, "content": "text", "bbox": None}]
        store = StudioStore(db_path=tmp_path / "notebooks.db")
        out = store.create("nb-1", "summary", "content", citations=citations)
        fetched = store.get("nb-1", out.id)
        assert fetched.citations == citations


# ---------------------------------------------------------------------------
# Unit tests: media provider clients
# ---------------------------------------------------------------------------

class _ProviderResponse:
    def __init__(self, payload, status_code=200, text="", headers=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestMiniMaxMediaClient:
    def test_media_client_prefers_media_specific_api_key(self, monkeypatch):
        from core.llm import minimax_media_client as media_client

        calls = []
        monkeypatch.setenv("MINIMAX_API_KEY", "text-key")
        monkeypatch.setenv("MINIMAX_MEDIA_API_KEY", "media-key")
        monkeypatch.setenv("MINIMAX_MEDIA_BASE_URL", "https://api.minimaxi.com")

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return _ProviderResponse({
                "data": {"audio": "00"},
                "trace_id": "trace-preferred",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            })

        monkeypatch.setattr(media_client.requests, "post", fake_post)

        media_client.generate_tts_audio("短句")

        _, headers, _, _ = calls[0]
        assert headers["Authorization"] == "Bearer media-key"

    def test_media_client_falls_back_to_text_api_key(self, monkeypatch):
        from core.llm import minimax_media_client as media_client

        calls = []
        monkeypatch.setenv("MINIMAX_API_KEY", "text-key")
        monkeypatch.delenv("MINIMAX_MEDIA_API_KEY", raising=False)
        monkeypatch.setenv("MINIMAX_MEDIA_BASE_URL", "https://api.minimaxi.com")

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return _ProviderResponse({
                "data": {"audio": "00"},
                "trace_id": "trace-fallback",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            })

        monkeypatch.setattr(media_client.requests, "post", fake_post)

        media_client.generate_tts_audio("短句")

        _, headers, _, _ = calls[0]
        assert headers["Authorization"] == "Bearer text-key"

    def test_tts_request_payload_and_hex_decode(self, monkeypatch):
        from core.llm import minimax_media_client as media_client

        calls = []
        monkeypatch.setenv("MINIMAX_MEDIA_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_MEDIA_BASE_URL", "https://api.minimaxi.com")
        monkeypatch.setenv("MINIMAX_TTS_MODEL", "speech-test")
        monkeypatch.setenv("MINIMAX_TTS_VOICE_ID", "voice-test")

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return _ProviderResponse({
                "data": {"audio": "000102ff"},
                "extra_info": {"audio_format": "mp3"},
                "trace_id": "trace-1",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            })

        monkeypatch.setattr(media_client.requests, "post", fake_post)

        result = media_client.generate_tts_audio("测试音频")

        assert result.data == bytes([0, 1, 2, 255])
        assert result.media_type == "audio/mpeg"
        assert result.file_extension == "mp3"
        url, headers, payload, _timeout = calls[0]
        assert url == "https://api.minimaxi.com/v1/t2a_v2"
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "speech-test"
        assert payload["output_format"] == "hex"
        assert payload["voice_setting"]["voice_id"] == "voice-test"

    def test_image_request_payload_and_base64_decode(self, monkeypatch):
        from core.llm import minimax_media_client as media_client

        calls = []
        image_bytes = b"jpeg-bytes"
        monkeypatch.setenv("MINIMAX_MEDIA_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_MEDIA_BASE_URL", "https://api.minimaxi.com")
        monkeypatch.setenv("MINIMAX_IMAGE_MODEL", "image-test")
        monkeypatch.setenv("MINIMAX_IMAGE_ASPECT_RATIO", "4:3")

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return _ProviderResponse({
                "data": {"image_base64": [base64.b64encode(image_bytes).decode("ascii")]},
                "trace_id": "trace-2",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            })

        monkeypatch.setattr(media_client.requests, "post", fake_post)

        result = media_client.generate_image("engineering infographic")

        assert result.data == image_bytes
        assert result.media_type == "image/jpeg"
        assert result.file_extension == "jpeg"
        url, headers, payload, _timeout = calls[0]
        assert url == "https://api.minimaxi.com/v1/image_generation"
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "image-test"
        assert payload["aspect_ratio"] == "4:3"
        assert payload["response_format"] == "base64"


class TestOpenAIImageClient:
    def test_image_request_payload_and_base64_decode(self, monkeypatch):
        from core.llm import openai_image_client as image_client

        calls = []
        image_bytes = b"openai-jpeg-bytes"
        monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "test-openai-key")
        monkeypatch.setenv("OPENAI_IMAGE_BASE_URL", "https://api.openai.com")
        monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-test")
        monkeypatch.setenv("OPENAI_IMAGE_SIZE", "1024x1024")
        monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "low")

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return _ProviderResponse(
                {"data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}]},
                headers={"x-request-id": "req-test"},
            )

        monkeypatch.setattr(image_client.requests, "post", fake_post)

        result = image_client.generate_image("COMAC infographic")

        assert result.data == image_bytes
        assert result.media_type == "image/jpeg"
        assert result.file_extension == "jpeg"
        assert result.trace_id == "req-test"
        url, headers, payload, _timeout = calls[0]
        assert url == "https://api.openai.com/v1/images/generations"
        assert headers["Authorization"] == "Bearer test-openai-key"
        assert payload["model"] == "gpt-image-test"
        assert payload["size"] == "1024x1024"
        assert payload["quality"] == "low"
        assert payload["output_format"] == "jpeg"


# ---------------------------------------------------------------------------
# API stubs installer
# ---------------------------------------------------------------------------

def _install_api_stubs():
    for name in ("sentence_transformers", "transformers", "torch"):
        sys.modules.setdefault(name, _stub(name))

    if "chromadb" not in sys.modules:
        chroma = _stub("chromadb")
        cfg = _stub("chromadb.config")
        cfg.Settings = dict
        chroma.PersistentClient = MagicMock
        chroma.config = cfg

    if "fitz" not in sys.modules:
        fitz = _stub("fitz")
        class _Matrix:
            def __init__(self, *a): pass
        fitz.Matrix = _Matrix
        fitz.open = MagicMock()

    for name in ["core.retrieval.embeddings", "core.retrieval.reranker",
                 "core.retrieval.vector_store", "core.retrieval.retriever"]:
        mod = sys.modules.setdefault(name, _stub(name))
        if not hasattr(mod, "EmbeddingManager"):
            mod.EmbeddingManager = MagicMock
        if not hasattr(mod, "CrossEncoderReranker"):
            mod.CrossEncoderReranker = MagicMock
        if not hasattr(mod, "VectorStoreAdapter"):
            mod.VectorStoreAdapter = MagicMock
        if not hasattr(mod, "RetrieverEngine"):
            mod.RetrieverEngine = MagicMock

    if "core.retrieval.retriever" not in sys.modules:
        retr_mod = _stub("core.retrieval.retriever")

        class _FakeRetrieverEngine:
            def __init__(self):
                self.graph_store = None
                self.graph_extractor = None

            def retrieve(self, *args, **kwargs):
                return []

        retr_mod.RetrieverEngine = _FakeRetrieverEngine

    for name in ["services.ingestion", "services.ingestion.service",
                 "services.ingestion.filenames", "services.ingestion.parser",
                 "services.ingestion.chunker"]:
        sys.modules.setdefault(name, _stub(name))
    svc = sys.modules["services.ingestion.service"]
    if not hasattr(svc, "IngestionService"):
        svc.IngestionService = MagicMock
    fn = sys.modules["services.ingestion.filenames"]
    if not hasattr(fn, "safe_upload_path"):
        fn.safe_upload_path = MagicMock()
        fn.validate_pdf_magic = MagicMock()

    for name in ["core.governance.gateway",
                 "core.models.source", "core.storage.notebook_store",
                 "core.storage.source_registry", "core.storage.graph_store",
                 "core.models.graph", "core.knowledge", "core.knowledge.graph_extractor"]:
        sys.modules.setdefault(name, _stub(name))

    gs_mod = sys.modules["core.storage.graph_store"]
    if not hasattr(gs_mod, "GraphStore"):
        gs_mod.GraphStore = MagicMock

    ge_mod = sys.modules["core.knowledge.graph_extractor"]
    if not hasattr(ge_mod, "GraphExtractor"):
        ge_mod.GraphExtractor = MagicMock

    gw = sys.modules["core.governance.gateway"]
    if not hasattr(gw, "AntiHallucinationGateway"):
        class _FakeGateway:
            @staticmethod
            def validate_and_parse(response, contexts):
                return True, response, []
        gw.AntiHallucinationGateway = _FakeGateway

    src_model = sys.modules["core.models.source"]
    if not hasattr(src_model, "SourceStatus"):
        class _SS:
            UPLOADING = "uploading"; PROCESSING = "processing"
            READY = "ready"; FAILED = "failed"
        src_model.SourceStatus = _SS

    for cls_name, mod_name in [("NotebookStore", "core.storage.notebook_store"),
                                ("SourceRegistry", "core.storage.source_registry")]:
        mod = sys.modules[mod_name]
        if not hasattr(mod, cls_name):
            setattr(mod, cls_name, MagicMock)


def _get_app(tmp_path):
    """Wire real stores to the API app for integration tests."""
    _install_api_stubs()
    for name in _REAL_MODULES + _PARENT_PACKAGES:
        sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)
    _patch_transaction()
    sys.modules.pop("apps.api.main", None)

    from core.storage.studio_store import StudioStore
    from core.storage.note_store import NoteStore
    from core.storage.chat_history_store import ChatHistoryStore

    import apps.api.main as api

    mock_nb = MagicMock(); mock_nb.id = "nb-1"; mock_nb.name = "Notebook One"
    mock_nb_store = MagicMock()
    mock_nb_store.get.side_effect = lambda nid: mock_nb if nid == "nb-1" else None

    api.notebook_store = mock_nb_store
    api.note_store = NoteStore(db_path=tmp_path / "notebooks.db")
    api.chat_history_store = ChatHistoryStore(db_path=tmp_path / "notebooks.db")
    api.studio_store = StudioStore(db_path=tmp_path / "notebooks.db")

    return api.app, api


# ---------------------------------------------------------------------------
# API tests: StudioStore CRUD endpoints
# ---------------------------------------------------------------------------

class TestStudioAPI:
    def test_list_empty(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.get("/api/v1/notebooks/nb-1/studio")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_and_delete(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        # Seed a studio output directly
        out = api.studio_store.create("nb-1", "summary", "Test content", citations=[])

        client = TestClient(app)
        # GET
        resp = client.get(f"/api/v1/notebooks/nb-1/studio/{out.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == out.id

        # DELETE
        resp = client.delete(f"/api/v1/notebooks/nb-1/studio/{out.id}")
        assert resp.status_code == 204
        assert client.get(f"/api/v1/notebooks/nb-1/studio/{out.id}").status_code == 404

    def test_save_as_note(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        out = api.studio_store.create("nb-1", "faq", "FAQ content", citations=[])

        client = TestClient(app)
        resp = client.post(f"/api/v1/notebooks/nb-1/studio/{out.id}/save-as-note")
        assert resp.status_code == 201
        note = resp.json()
        assert note["content"] == "FAQ content"
        # Verify note is in note store
        notes = client.get("/api/v1/notebooks/nb-1/notes").json()
        assert len(notes) == 1

    def test_404_unknown_notebook(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        assert client.get("/api/v1/notebooks/ghost/studio").status_code == 404

    def test_404_unknown_output(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        assert client.get("/api/v1/notebooks/nb-1/studio/ghost-id").status_code == 404

    def test_delete_404_unknown_output(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        assert client.delete("/api/v1/notebooks/nb-1/studio/ghost-id").status_code == 404

    def test_export_studio_to_obsidian(self, tmp_path):
        from fastapi.testclient import TestClient
        from pathlib import Path
        from core.integrations.obsidian_export import ObsidianVault

        app, api = _get_app(tmp_path)
        out = api.studio_store.create("nb-1", "faq", "FAQ content", citations=[])
        client = TestClient(app)

        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        original_get_obsidian_vault = api.get_obsidian_vault
        api.get_obsidian_vault = lambda: ObsidianVault(name="vault", path=vault_path)

        try:
            resp = client.post(
                f"/api/v1/notebooks/nb-1/studio/{out.id}/export/obsidian"
            )
            assert resp.status_code == 200
            data = resp.json()
            exported_path = Path(data["file_path"])
            assert exported_path.exists()
            assert exported_path.read_text(encoding="utf-8").find("FAQ content") >= 0
        finally:
            api.get_obsidian_vault = original_get_obsidian_vault


# ---------------------------------------------------------------------------
# API tests: generate endpoint
# ---------------------------------------------------------------------------

class TestStudioGenerate:
    def _make_mock_source(self, status="ready"):
        src = MagicMock()
        src.id = "src-1"
        src.status = status
        return src

    def _mock_retriever(self, api, chunks):
        """Replace retriever with a stub that returns given chunks."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = chunks
        api.retriever_engine = mock_retriever

    def test_generate_404_unknown_notebook(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/ghost/studio/generate",
                           json={"output_type": "summary"})
        assert resp.status_code == 404

    def test_generate_422_invalid_type(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                           json={"output_type": "invalid_type"})
        assert resp.status_code == 422

    def test_generate_422_no_sources(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        # source_registry returns empty list
        api.source_registry = MagicMock()
        api.source_registry.list_by_notebook.return_value = []
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                           json={"output_type": "summary"})
        assert resp.status_code == 422

    def test_generate_503_llm_unavailable(self, tmp_path):
        from fastapi.testclient import TestClient
        from core.storage.studio_store import StudioStore
        app, api = _get_app(tmp_path)

        # Mock source registry with a ready source
        api.source_registry = MagicMock()
        api.source_registry.list_by_notebook.return_value = [self._make_mock_source()]

        # Mock retriever to return some chunks
        self._mock_retriever(api, [{"text": "chunk", "metadata": {"source": "a.pdf", "page": 1}}])

        # Make LLM raise LLMUnavailableError
        import apps.api.main as api_mod
        original_invoke = api_mod.invoke_local_llm
        def fail_llm(*args, **kwargs):
            raise api_mod.LLMUnavailableError("LLM unreachable")
        api_mod.invoke_local_llm = fail_llm

        try:
            client = TestClient(app)
            resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                               json={"output_type": "summary"})
            assert resp.status_code == 503
        finally:
            api_mod.invoke_local_llm = original_invoke

    def test_generate_success(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)

        # Mock sources
        api.source_registry = MagicMock()
        api.source_registry.list_by_notebook.return_value = [self._make_mock_source()]

        # Mock retriever
        self._mock_retriever(api, [
            {"text": "这是测试内容", "metadata": {"source": "test.pdf", "page": 1}}
        ])

        # Mock LLM to return canned response
        import apps.api.main as api_mod
        original_invoke = api_mod.invoke_local_llm
        api_mod.invoke_local_llm = lambda system_prompt, user_query: "生成的摘要内容。"

        try:
            client = TestClient(app)
            resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                               json={"output_type": "summary"})
            assert resp.status_code == 201
            data = resp.json()
            assert data["output_type"] == "summary"
            assert data["content"] == "生成的摘要内容。"
            assert "id" in data

            # Verify persisted in studio store
            items = client.get("/api/v1/notebooks/nb-1/studio").json()
            assert len(items) == 1
            assert items[0]["id"] == data["id"]
        finally:
            api_mod.invoke_local_llm = original_invoke

    def test_generate_all_output_types(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        monkeypatch.delenv("ENABLE_STUDIO_MEDIA_GENERATION", raising=False)
        monkeypatch.delenv("ENABLE_EXTERNAL_MEDIA_GENERATION", raising=False)
        app, api = _get_app(tmp_path)

        api.source_registry = MagicMock()
        api.source_registry.list_by_notebook.return_value = [self._make_mock_source()]
        self._mock_retriever(api, [
            {"text": "内容", "metadata": {"source": "a.pdf", "page": 1}}
        ])

        import apps.api.main as api_mod
        original_invoke = api_mod.invoke_local_llm
        api_mod.invoke_local_llm = lambda system_prompt, user_query: "生成的内容。"

        try:
            client = TestClient(app)
            for ot in ("summary", "faq", "briefing", "glossary", "action_items", "podcast", "infographic"):
                resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                                   json={"output_type": ot})
                assert resp.status_code == 201, f"Failed for output_type={ot}: {resp.text}"
                payload = resp.json()
                assert payload["output_type"] == ot
                if ot in {"podcast", "infographic"}:
                    assert payload["has_media"] is False
                    assert payload["media_url"] is None
                    assert "media_blocked_reason" in payload
        finally:
            api_mod.invoke_local_llm = original_invoke

    def test_generate_podcast_creates_media_only_when_explicitly_enabled(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from core.llm.media_types import GeneratedMedia
        from core.llm import minimax_media_client

        monkeypatch.setenv("ENABLE_STUDIO_MEDIA_GENERATION", "1")
        app, api = _get_app(tmp_path)
        api.DEFAULT_SPACES_DIR = tmp_path / "spaces"

        api.source_registry = MagicMock()
        api.source_registry.list_by_notebook.return_value = [self._make_mock_source()]
        self._mock_retriever(api, [
            {"text": "反推展开需要轮载、解锁和转速限制。", "metadata": {"source": "a.pdf", "page": 1}}
        ])
        monkeypatch.setattr(api, "invoke_configured_llm", lambda system_prompt, user_query: "播客脚本。")
        monkeypatch.setattr(
            minimax_media_client,
            "generate_tts_audio",
            lambda text: GeneratedMedia(data=b"mp3-bytes", media_type="audio/mpeg", file_extension="mp3"),
        )

        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/nb-1/studio/generate", json={"output_type": "podcast"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["output_type"] == "podcast"
        assert data["has_media"] is True
        media_resp = client.get(data["media_url"])
        assert media_resp.status_code == 200
        assert media_resp.content == b"mp3-bytes"

    def test_media_endpoint_serves_generated_file(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        out = api.studio_store.create("nb-1", "podcast", "播客脚本", citations=[])
        api._write_studio_media("nb-1", out.id, "podcast", b"fake-mp3")

        client = TestClient(app)
        resp = client.get(f"/api/v1/notebooks/nb-1/studio/{out.id}/media")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/mpeg")
        assert resp.content == b"fake-mp3"

    def test_media_endpoint_404_when_file_missing(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        out = api.studio_store.create("nb-1", "infographic", "image prompt", citations=[])

        client = TestClient(app)
        resp = client.get(f"/api/v1/notebooks/nb-1/studio/{out.id}/media")

        assert resp.status_code == 404
