"""
test_notes_history.py
======================
Tests for S-20: Notes CRUD, ChatHistory persistence, and API endpoints.

  * NoteStore: create, list, get, update, delete
  * ChatHistoryStore: append, list, clear, FIFO eviction
  * API: GET/POST/PATCH/DELETE /notes, GET/DELETE /history

Design constraint: the unit tests (TestNoteStore, TestChatHistoryStore) import
the *real* store classes; we must NEVER stub those modules.  The API tests
import apps.api.main which drags in heavy deps — those are stubbed via
sys.modules before the import.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared stub helper
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Transaction stub (needed by both store unit tests and API tests)
# We set real helpers so store paths resolve correctly.
# ---------------------------------------------------------------------------

def _patch_transaction():
    """Ensure the transaction stub exists with all attributes note_store needs.
    Only adds missing attributes — does NOT overwrite existing ones, to avoid
    breaking test_crash_recovery / test_ingest_transaction which use real impls.
    """
    name = "core.ingestion.transaction"
    mod = sys.modules.get(name)
    if mod is None:
        mod = _stub(name)
    if not hasattr(mod, "DEFAULT_SPACES_DIR"):
        mod.DEFAULT_SPACES_DIR = "data/spaces"
    if not hasattr(mod, "resolve_space_path"):
        mod.resolve_space_path = lambda nb, fn, base_dir=None: \
            Path(str(base_dir or "data/spaces")) / nb / fn
    if not hasattr(mod, "utc_now_iso"):
        mod.utc_now_iso = lambda: "2026-04-16T00:00:00Z"
    if not hasattr(mod, "IngestTransaction"):
        mod.IngestTransaction = MagicMock
    if not hasattr(mod, "cleanup_committed_transactions"):
        mod.cleanup_committed_transactions = MagicMock()
    if not hasattr(mod, "iter_space_ids"):
        mod.iter_space_ids = MagicMock(return_value=[])
    if not hasattr(mod, "recover_incomplete_transactions"):
        mod.recover_incomplete_transactions = MagicMock()
    if not hasattr(mod, "summarize_transaction_health"):
        mod.summarize_transaction_health = MagicMock(return_value={})


_patch_transaction()

# ---------------------------------------------------------------------------
# Evict any stale stubs for the modules we want to import REAL
# (runs at collection time; the fixture below repeats this before each test
#  to handle cross-file stub contamination when tests run together)
# ---------------------------------------------------------------------------
_REAL_STORE_MODULES = (
    "core.storage.note_store", "core.storage.chat_history_store",
    "core.models.note", "core.models.chat_message",
)
# Also need to evict parent package stubs that block real submodule imports.
# test_cross_notebook_isolation does _stub("core.storage") and _stub("core.models")
# which turns those packages into plain ModuleType objects.
_REAL_PARENT_PACKAGES = ("core.storage", "core.models")

for _m in _REAL_STORE_MODULES:
    sys.modules.pop(_m, None)


@pytest.fixture(autouse=True)
def _evict_store_stubs():
    """Re-evict store stubs before every test so cross-file contamination
    (e.g. test_cross_notebook_isolation._stub('core.storage')) doesn't block
    real submodule imports.  Also ensure the transaction stub has the
    attributes note_store.py needs for its from-import."""
    for name in _REAL_STORE_MODULES + _REAL_PARENT_PACKAGES:
        sys.modules.pop(name, None)
    # Evict transaction too so note_store.py can re-import it cleanly; then
    # re-patch so the stub (or real module) has everything note_store needs.
    sys.modules.pop("core.ingestion.transaction", None)
    _patch_transaction()
    yield
    # Teardown: evict store modules so the next test also gets a fresh import
    for name in _REAL_STORE_MODULES + _REAL_PARENT_PACKAGES:
        sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)


# ---------------------------------------------------------------------------
# Unit tests: NoteStore (uses REAL implementation)
# ---------------------------------------------------------------------------

class TestNoteStore:
    def test_create_and_list(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "This is a test answer.", citations=[], title="Test Note")
        notes = store.list_by_notebook("nb-1")
        assert len(notes) == 1
        assert notes[0].id == note.id
        assert notes[0].title == "Test Note"

    def test_default_title_truncation(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "A" * 100, citations=[])
        assert len(note.title) <= 41  # 40 chars + ellipsis char

    def test_get(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "content", citations=[])
        fetched = store.get("nb-1", note.id)
        assert fetched is not None
        assert fetched.id == note.id

    def test_get_missing_returns_none(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        assert store.get("nb-1", "ghost") is None

    def test_update_title(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "original", citations=[])
        updated = store.update("nb-1", note.id, title="Updated Title")
        assert updated.title == "Updated Title"
        assert store.get("nb-1", note.id).title == "Updated Title"

    def test_update_missing_raises_key_error(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        with pytest.raises(KeyError):
            store.update("nb-1", "ghost", title="x")

    def test_delete(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "to delete", citations=[])
        assert store.delete("nb-1", note.id) is True
        assert store.get("nb-1", note.id) is None

    def test_delete_missing_returns_false(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        assert store.delete("nb-1", "ghost") is False

    def test_notebooks_isolated(self, tmp_path):
        from core.storage.note_store import NoteStore
        store = NoteStore(spaces_dir=tmp_path)
        store.create("nb-a", "note A", citations=[])
        store.create("nb-b", "note B", citations=[])
        assert len(store.list_by_notebook("nb-a")) == 1
        assert len(store.list_by_notebook("nb-b")) == 1

    def test_citations_persisted(self, tmp_path):
        from core.storage.note_store import NoteStore
        citations = [{"source_file": "a.pdf", "page_number": 1, "content": "text", "bbox": None}]
        store = NoteStore(spaces_dir=tmp_path)
        note = store.create("nb-1", "content", citations=citations)
        fetched = store.get("nb-1", note.id)
        assert fetched.citations == citations


# ---------------------------------------------------------------------------
# Unit tests: ChatHistoryStore (uses REAL implementation)
# ---------------------------------------------------------------------------

class TestChatHistoryStore:
    def test_append_and_list(self, tmp_path):
        from core.storage.chat_history_store import ChatHistoryStore
        store = ChatHistoryStore(spaces_dir=tmp_path)
        store.append("nb-1", "user", "Hello")
        store.append("nb-1", "assistant", "Hi there", citations=[], is_fully_verified=True)
        msgs = store.list_by_notebook("nb-1")
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        assert msgs[1].is_fully_verified is True

    def test_list_limit(self, tmp_path):
        from core.storage.chat_history_store import ChatHistoryStore
        store = ChatHistoryStore(spaces_dir=tmp_path)
        for i in range(10):
            store.append("nb-1", "user", f"msg {i}")
        msgs = store.list_by_notebook("nb-1", limit=5)
        assert len(msgs) == 5
        assert msgs[-1].content == "msg 9"

    def test_clear(self, tmp_path):
        from core.storage.chat_history_store import ChatHistoryStore
        store = ChatHistoryStore(spaces_dir=tmp_path)
        store.append("nb-1", "user", "hello")
        store.append("nb-1", "assistant", "world")
        count = store.clear("nb-1")
        assert count == 2
        assert store.list_by_notebook("nb-1") == []

    def test_fifo_eviction(self, tmp_path):
        from core.storage.chat_history_store import ChatHistoryStore, MAX_HISTORY
        store = ChatHistoryStore(spaces_dir=tmp_path)
        for i in range(MAX_HISTORY + 5):
            store.append("nb-1", "user", f"msg {i}")
        msgs = store.list_by_notebook("nb-1", limit=0)
        assert len(msgs) == MAX_HISTORY
        assert msgs[0].content == "msg 5"  # oldest 5 evicted

    def test_notebooks_isolated(self, tmp_path):
        from core.storage.chat_history_store import ChatHistoryStore
        store = ChatHistoryStore(spaces_dir=tmp_path)
        store.append("nb-a", "user", "in A")
        store.append("nb-b", "user", "in B")
        assert len(store.list_by_notebook("nb-a")) == 1
        assert len(store.list_by_notebook("nb-b")) == 1


# ---------------------------------------------------------------------------
# Heavy stubs — only installed just before API tests that need main.py
# We DO NOT stub core.storage.note_store or chat_history_store here.
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
                 "core.retrieval.vector_store"]:
        mod = sys.modules.setdefault(name, _stub(name))
        if not hasattr(mod, "EmbeddingManager"):
            mod.EmbeddingManager = MagicMock
        if not hasattr(mod, "CrossEncoderReranker"):
            mod.CrossEncoderReranker = MagicMock
        if not hasattr(mod, "VectorStoreAdapter"):
            mod.VectorStoreAdapter = MagicMock

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

    for name in ["core.governance.prompts", "core.governance.gateway",
                 "core.models.source", "core.storage.notebook_store",
                 "core.storage.source_registry"]:
        sys.modules.setdefault(name, _stub(name))

    prompts = sys.modules["core.governance.prompts"]
    if not hasattr(prompts, "QA_SYSTEM_PROMPT"):
        prompts.QA_SYSTEM_PROMPT = "{context_blocks}"
        prompts.build_context_block = lambda x: str(x)
    gw = sys.modules["core.governance.gateway"]
    if not hasattr(gw, "AntiHallucinationGateway"):
        class _FakeGateway:
            @staticmethod
            def validate_and_parse(response, contexts):
                return True, response, []
        gw.AntiHallucinationGateway = _FakeGateway

    sm = sys.modules["core.models.source"]
    if not hasattr(sm, "SourceStatus"):
        class _SS:
            UPLOADING = "uploading"; PROCESSING = "processing"
            READY = "ready"; FAILED = "failed"
        sm.SourceStatus = _SS

    for cls_name, mod_name in [("NotebookStore", "core.storage.notebook_store"),
                                ("SourceRegistry", "core.storage.source_registry")]:
        mod = sys.modules[mod_name]
        if not hasattr(mod, cls_name):
            setattr(mod, cls_name, MagicMock)


def _get_app(tmp_path):
    """Import (or reuse) apps.api.main and wire real stores to it."""
    _install_api_stubs()
    # Evict stale stub registrations for our real store modules so the real
    # implementations are used in the API endpoints
    for name in ("core.storage.note_store", "core.storage.chat_history_store",
                 "core.models.note", "core.models.chat_message"):
        sys.modules.pop(name, None)

    # Re-import real stores fresh
    from core.storage.note_store import NoteStore
    from core.storage.chat_history_store import ChatHistoryStore

    if "apps.api.main" in sys.modules:
        api = sys.modules["apps.api.main"]
    else:
        import apps.api.main as api

    # Notebook mock
    mock_nb = MagicMock(); mock_nb.id = "nb-1"
    mock_nb_store = MagicMock()
    mock_nb_store.get.side_effect = lambda nid: mock_nb if nid == "nb-1" else None

    api.notebook_store = mock_nb_store
    api.note_store = NoteStore(spaces_dir=tmp_path)
    api.chat_history_store = ChatHistoryStore(spaces_dir=tmp_path)

    return api.app, api


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class TestNotesAPI:
    def test_create_and_list_notes(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/nb-1/notes",
                           json={"content": "AI said this", "citations": [], "title": "My Note"})
        assert resp.status_code == 201
        note = resp.json()
        assert note["title"] == "My Note"
        list_resp = client.get("/api/v1/notebooks/nb-1/notes")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

    def test_get_note(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        created = client.post("/api/v1/notebooks/nb-1/notes",
                              json={"content": "test", "citations": []}).json()
        resp = client.get(f"/api/v1/notebooks/nb-1/notes/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_patch_note(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        created = client.post("/api/v1/notebooks/nb-1/notes",
                              json={"content": "original", "citations": []}).json()
        resp = client.patch(f"/api/v1/notebooks/nb-1/notes/{created['id']}",
                            json={"title": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_delete_note(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        created = client.post("/api/v1/notebooks/nb-1/notes",
                              json={"content": "delete me", "citations": []}).json()
        resp = client.delete(f"/api/v1/notebooks/nb-1/notes/{created['id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/v1/notebooks/nb-1/notes/{created['id']}").status_code == 404

    def test_notes_404_unknown_notebook(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        assert client.get("/api/v1/notebooks/ghost/notes").status_code == 404


class TestChatHistoryAPI:
    def test_get_empty_history(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.get("/api/v1/notebooks/nb-1/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_clear_history(self, tmp_path):
        from fastapi.testclient import TestClient
        app, api = _get_app(tmp_path)
        # Seed history directly via the wired store
        api.chat_history_store.append("nb-1", "user", "hi")
        api.chat_history_store.append("nb-1", "assistant", "hello")

        client = TestClient(app)
        resp = client.delete("/api/v1/notebooks/nb-1/history")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert client.get("/api/v1/notebooks/nb-1/history").json() == []

    def test_history_404_unknown_notebook(self, tmp_path):
        from fastapi.testclient import TestClient
        app, _ = _get_app(tmp_path)
        client = TestClient(app)
        assert client.get("/api/v1/notebooks/ghost/history").status_code == 404
