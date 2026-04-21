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
        for t in ("summary", "faq", "briefing", "glossary", "action_items"):
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

    def test_generate_all_output_types(self, tmp_path):
        from fastapi.testclient import TestClient
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
            for ot in ("summary", "faq", "briefing", "glossary", "action_items"):
                resp = client.post("/api/v1/notebooks/nb-1/studio/generate",
                                   json={"output_type": ot})
                assert resp.status_code == 201, f"Failed for output_type={ot}: {resp.text}"
                assert resp.json()["output_type"] == ot
        finally:
            api_mod.invoke_local_llm = original_invoke
