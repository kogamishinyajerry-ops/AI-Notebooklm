"""
test_pdf_serve.py
==================
Tests for S-19: PDF file serve and page image render endpoints.

  * GET /api/v1/notebooks/{nb}/sources/{src}/file  → PDF bytes
  * GET /api/v1/notebooks/{nb}/sources/{src}/pages/{page} → PNG bytes
  * Path traversal attack returns 403
  * Out-of-range page returns 422

All heavy deps (fitz/PyMuPDF, ML stack) are stubbed.
"""
from __future__ import annotations

import sys
import types
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs (reuse pattern from test_cross_notebook_isolation)
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs():
    if "fitz" not in sys.modules:
        fitz = _stub("fitz")
        # Matrix class stub
        class _Matrix:
            def __init__(self, *args): pass
        fitz.Matrix = _Matrix
        fitz.open = MagicMock()

    for name in ("sentence_transformers", "transformers", "torch"):
        if name not in sys.modules:
            _stub(name)

    if "chromadb" not in sys.modules:
        chroma = _stub("chromadb")
        cfg = _stub("chromadb.config")
        cfg.Settings = dict
        chroma.PersistentClient = MagicMock
        chroma.config = cfg

    for name in [
        "core.retrieval.embeddings", "core.retrieval.reranker",
        "core.retrieval.vector_store", "services.ingestion",
        "services.ingestion.service", "services.ingestion.filenames",
        "services.ingestion.parser", "services.ingestion.chunker",
        "core.ingestion.transaction",
    ]:
        if name not in sys.modules:
            _stub(name)

    tx_mod = sys.modules["core.ingestion.transaction"]
    if not hasattr(tx_mod, "IngestTransaction"):
        tx_mod.IngestTransaction = MagicMock
        tx_mod.cleanup_committed_transactions = MagicMock()
        tx_mod.iter_space_ids = MagicMock(return_value=[])
        tx_mod.recover_incomplete_transactions = MagicMock()
        tx_mod.summarize_transaction_health = MagicMock(return_value={})
        tx_mod.DEFAULT_SPACES_DIR = "data/spaces"
        tx_mod.resolve_space_path = lambda nb, fn, base_dir=None: Path(str(base_dir or "data/spaces")) / nb / fn
        tx_mod.utc_now_iso = lambda: "2026-01-01T00:00:00Z"

    emb = sys.modules["core.retrieval.embeddings"]
    if not hasattr(emb, "EmbeddingManager"):
        emb.EmbeddingManager = MagicMock
    rer = sys.modules["core.retrieval.reranker"]
    if not hasattr(rer, "CrossEncoderReranker"):
        rer.CrossEncoderReranker = MagicMock
    vs = sys.modules["core.retrieval.vector_store"]
    if not hasattr(vs, "VectorStoreAdapter"):
        vs.VectorStoreAdapter = MagicMock

    svc = sys.modules["services.ingestion.service"]
    if not hasattr(svc, "IngestionService"):
        svc.IngestionService = MagicMock
    fn = sys.modules["services.ingestion.filenames"]
    if not hasattr(fn, "safe_upload_path"):
        fn.safe_upload_path = MagicMock()
        fn.validate_pdf_magic = MagicMock()

    for name in ["core.governance.prompts", "core.governance.gateway",
                 "core.models.source", "core.storage.notebook_store",
                 "core.storage.source_registry", "core.storage.note_store",
                 "core.storage.chat_history_store", "core.storage.studio_store",
                 "core.models.studio_output"]:
        if name not in sys.modules:
            _stub(name)

    prompts = sys.modules["core.governance.prompts"]
    if not hasattr(prompts, "QA_SYSTEM_PROMPT"):
        prompts.QA_SYSTEM_PROMPT = "{context_blocks}"
        prompts.build_context_block = lambda x: str(x)
    if not hasattr(prompts, "STUDIO_PROMPTS"):
        prompts.STUDIO_PROMPTS = {t: "{context_blocks}" for t in
            ("summary", "faq", "briefing", "glossary", "action_items")}

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
            UPLOADING = "uploading"
            PROCESSING = "processing"
            READY = "ready"
            FAILED = "failed"
        src_model.SourceStatus = _SS

    nb_mod = sys.modules["core.storage.notebook_store"]
    if not hasattr(nb_mod, "NotebookStore"):
        nb_mod.NotebookStore = MagicMock

    sr_mod = sys.modules["core.storage.source_registry"]
    if not hasattr(sr_mod, "SourceRegistry"):
        sr_mod.SourceRegistry = MagicMock

    ns_mod = sys.modules["core.storage.note_store"]
    if not hasattr(ns_mod, "NoteStore"):
        ns_mod.NoteStore = MagicMock

    ch_mod = sys.modules["core.storage.chat_history_store"]
    if not hasattr(ch_mod, "ChatHistoryStore"):
        ch_mod.ChatHistoryStore = MagicMock

    ss_mod = sys.modules["core.storage.studio_store"]
    if not hasattr(ss_mod, "StudioStore"):
        ss_mod.StudioStore = MagicMock

    so_mod = sys.modules["core.models.studio_output"]
    if not hasattr(so_mod, "StudioOutputType"):
        class _SOT:
            @staticmethod
            def values():
                return ["summary", "faq", "briefing", "glossary", "action_items"]
        so_mod.StudioOutputType = _SOT


_install_stubs()


# ---------------------------------------------------------------------------
# Per-test fixture: re-run stub setup so cross-file contamination from other
# test modules (e.g. test_cross_notebook_isolation._install_stubs which leaves
# core.storage as a plain module rather than a package stub) doesn't corrupt
# the fitz/governance stubs we depend on.
# ---------------------------------------------------------------------------

import pytest as _pytest  # noqa: E402

@_pytest.fixture(autouse=True)
def _reinstall_stubs_per_test():
    # Force-reset fitz stub so the Matrix class and open mock are always fresh
    fitz_stub = sys.modules.get("fitz")
    if fitz_stub is not None:
        class _Matrix:
            def __init__(self, *args): pass
        fitz_stub.Matrix = _Matrix
        fitz_stub.open = MagicMock()
    # Re-run full stub install (setdefault / if-not-hasattr guards keep it safe)
    _install_stubs()
    yield


# ---------------------------------------------------------------------------
# Helper: build app with mocked notebook + source
# ---------------------------------------------------------------------------

def _build_app(tmp_path: Path, source_status="ready", page_count=5):
    """Return (app, source_file_path) with all singletons mocked."""
    import apps.api.main as api_main
    from fastapi.testclient import TestClient

    # Create a real PDF-like file in tmp_path (just bytes, fitz is mocked)
    docs_dir = tmp_path / "nb-1" / "docs"
    docs_dir.mkdir(parents=True)
    pdf_file = docs_dir / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock content")

    # Notebook mock
    mock_nb = MagicMock(); mock_nb.id = "nb-1"
    mock_nb_store = MagicMock()
    mock_nb_store.get.side_effect = lambda nid: mock_nb if nid == "nb-1" else None

    # Source mock
    mock_src = MagicMock()
    mock_src.id = "src-1"
    mock_src.filename = "test.pdf"
    mock_src.file_path = str(pdf_file)
    mock_src.page_count = page_count
    mock_src.status = source_status

    mock_src_reg = MagicMock()
    mock_src_reg.get.side_effect = lambda nb, sid: mock_src if (nb == "nb-1" and sid == "src-1") else None
    mock_src_reg.spaces_dir = tmp_path

    api_main.notebook_store = mock_nb_store
    api_main.source_registry = mock_src_reg

    return api_main.app, pdf_file


# ---------------------------------------------------------------------------
# S-19a: PDF file serve
# ---------------------------------------------------------------------------

def test_serve_source_file_returns_pdf(tmp_path):
    """GET /file must return the raw PDF bytes with correct content-type."""
    from fastapi.testclient import TestClient
    app, pdf_file = _build_app(tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v1/notebooks/nb-1/sources/src-1/file")

    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert resp.content == pdf_file.read_bytes()


def test_serve_source_file_404_unknown_notebook(tmp_path):
    from fastapi.testclient import TestClient
    app, _ = _build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/v1/notebooks/ghost/sources/src-1/file")
    assert resp.status_code == 404


def test_serve_source_file_404_unknown_source(tmp_path):
    from fastapi.testclient import TestClient
    app, _ = _build_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/v1/notebooks/nb-1/sources/ghost-src/file")
    assert resp.status_code == 404


def test_serve_source_file_path_traversal_blocked(tmp_path):
    """
    A source whose file_path points outside spaces_dir must return 403.
    """
    import apps.api.main as api_main
    from fastapi.testclient import TestClient

    # Place the file outside tmp_path (simulates tampered registry)
    outside_file = tmp_path.parent / "secret.pdf"
    outside_file.write_bytes(b"secret")

    mock_nb = MagicMock(); mock_nb.id = "nb-1"
    mock_nb_store = MagicMock()
    mock_nb_store.get.side_effect = lambda nid: mock_nb if nid == "nb-1" else None

    mock_src = MagicMock()
    mock_src.id = "evil-src"
    mock_src.filename = "secret.pdf"
    mock_src.file_path = str(outside_file)
    mock_src.page_count = 1

    mock_src_reg = MagicMock()
    mock_src_reg.get.return_value = mock_src
    mock_src_reg.spaces_dir = tmp_path  # file is outside this

    api_main.notebook_store = mock_nb_store
    api_main.source_registry = mock_src_reg

    client = TestClient(api_main.app)
    resp = client.get("/api/v1/notebooks/nb-1/sources/evil-src/file")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# S-19a: Page image render
# ---------------------------------------------------------------------------

def test_render_page_returns_png(tmp_path):
    """GET /pages/1 must return PNG bytes when fitz renders successfully."""
    import apps.api.main as api_main
    from fastapi.testclient import TestClient

    # Build app with real file
    app, _ = _build_app(tmp_path)

    # Mock fitz so page render returns minimal PNG bytes
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # minimal PNG header
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = fake_png
    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pix
    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_doc.close = MagicMock()
    sys.modules["fitz"].open = MagicMock(return_value=mock_doc)

    client = TestClient(app)
    resp = client.get("/api/v1/notebooks/nb-1/sources/src-1/pages/1")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == fake_png


def test_render_page_out_of_range_returns_422(tmp_path):
    """Page number beyond page_count must return 422."""
    from fastapi.testclient import TestClient
    app, _ = _build_app(tmp_path, page_count=3)
    client = TestClient(app)

    resp = client.get("/api/v1/notebooks/nb-1/sources/src-1/pages/99")
    assert resp.status_code == 422


def test_render_page_zero_returns_422(tmp_path):
    """Page 0 (below 1-indexed minimum) must return 422."""
    from fastapi.testclient import TestClient
    app, _ = _build_app(tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v1/notebooks/nb-1/sources/src-1/pages/0")
    assert resp.status_code == 422
