"""
test_cross_notebook_isolation.py
=================================
Verifies that per-notebook source scoping works end-to-end:

  * Notebook A (sources 1, 2) must not retrieve chunks from Notebook B (source 3).
  * After source 2 is logically removed its source_id must be absent from the
    where-filter passed to the vector store.
  * When the LLM service is unavailable the chat endpoint must return HTTP 503
    (no mock fallback).

All expensive dependencies (chromadb, PyMuPDF, sentence_transformers, vLLM)
are stubbed via sys.modules so the suite runs fully offline under C1.
"""
from __future__ import annotations

import sys
import types
import uuid
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper to create a named stub module
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Shared fake primitives (used by both retriever-level and API-level tests)
# ---------------------------------------------------------------------------

class FakeEmbedding:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeEmbeddingManager:
    def encode(self, texts):
        return [FakeEmbedding([0.1, 0.2, 0.3])]


class FakeReranker:
    def rerank(self, query, chunks, top_n):
        return chunks[:top_n]


class RecordingVectorStore:
    """
    Fake VectorStoreAdapter that records the ``where`` filter passed to
    ``query()`` and returns a deterministic corpus keyed by source_id.
    """

    CORPUS = {
        "src-1": [("chunk from source 1", {"source": "doc1.pdf", "page": "1", "source_id": "src-1"})],
        "src-2": [("chunk from source 2", {"source": "doc2.pdf", "page": "2", "source_id": "src-2"})],
        "src-3": [("chunk from source 3", {"source": "doc3.pdf", "page": "1", "source_id": "src-3"})],
    }

    def __init__(self):
        self.last_where = None

    def query(self, query_embeddings, top_k=5, where=None):
        self.last_where = where

        if where is None:
            allowed_ids = list(self.CORPUS.keys())
        elif "$in" in where.get("source_id", {}):
            allowed_ids = where["source_id"]["$in"]
        elif "$eq" in where.get("source_id", {}):
            allowed_ids = [where["source_id"]["$eq"]]
        else:
            allowed_ids = list(self.CORPUS.keys())

        docs, metas = [], []
        for sid in allowed_ids:
            for doc, meta in self.CORPUS.get(sid, []):
                docs.append(doc)
                metas.append(meta)

        if not docs:
            return {"documents": [[]], "metadatas": [[]]}
        return {"documents": [docs], "metadatas": [metas]}

    def delete(self, ids=None, where=None):
        pass

    def new_document_ids(self, count):
        return [str(uuid.uuid4()) for _ in range(count)]

    def add_documents(self, chunks, metadatas, embeddings, ids=None):
        return ids or self.new_document_ids(len(chunks))


# ---------------------------------------------------------------------------
# Stub all heavy dependencies BEFORE any project module is imported.
# We do this at function call time (inside a fixture-like helper) to avoid
# polluting the global sys.modules for tests that don't need stubs.
# ---------------------------------------------------------------------------

_stubs_installed = False


def _install_stubs():
    global _stubs_installed
    if _stubs_installed:
        return
    _stubs_installed = True

    # ---- sentence_transformers ----
    st = _stub("sentence_transformers")
    st.SentenceTransformer = MagicMock

    # ---- chromadb ----
    chroma = _stub("chromadb")
    chroma_cfg = _stub("chromadb.config")
    chroma_cfg.Settings = dict
    chroma.PersistentClient = MagicMock
    chroma.config = chroma_cfg

    # ---- PyMuPDF (fitz) ----
    fitz = _stub("fitz")
    fitz.open = MagicMock(return_value=MagicMock(page_count=1))

    # ---- core.retrieval sub-modules ----
    # We stub these before RetrieverEngine is imported so the from-imports
    # inside retriever.py resolve against our fakes.
    emb_mod = _stub("core.retrieval.embeddings")
    emb_mod.EmbeddingManager = FakeEmbeddingManager

    rer_mod = _stub("core.retrieval.reranker")

    class _FakeCrossEncoder:
        def rerank(self, query, chunks, top_n):
            return chunks[:top_n]

    rer_mod.CrossEncoderReranker = _FakeCrossEncoder

    vs_mod = _stub("core.retrieval.vector_store")
    vs_mod.VectorStoreAdapter = RecordingVectorStore

    class _FakeBM25Index:
        """Stub BM25 index: always empty (size=0) so hybrid degrades to vector-only."""
        size = 0
        def build(self, corpus): pass
        def query(self, query, top_k=10, extra_tokens=None): return []

    bm25_mod = _stub("core.retrieval.bm25_index")
    bm25_mod.BM25Index = _FakeBM25Index

    class _FakeQueryExpander:
        """Stub query expander: no-op (returns original query, no extra tokens)."""
        def expand(self, query):
            return query, []

    qe_mod = _stub("core.retrieval.query_expander")
    qe_mod.QueryExpander = _FakeQueryExpander

    # ---- services.ingestion ----
    _stub("services.ingestion")
    svc_mod = _stub("services.ingestion.service")

    class _FakeIngestionService:
        vector_store = RecordingVectorStore()

    svc_mod.IngestionService = _FakeIngestionService

    fn_mod = _stub("services.ingestion.filenames")
    fn_mod.safe_upload_path = MagicMock()
    fn_mod.validate_pdf_magic = MagicMock()

    _stub("services.ingestion.parser")
    _stub("services.ingestion.chunker")

    # ---- core.ingestion.transaction ----
    tx_mod = _stub("core.ingestion.transaction")
    tx_mod.IngestTransaction = MagicMock
    tx_mod.cleanup_committed_transactions = MagicMock()
    tx_mod.iter_space_ids = MagicMock(return_value=[])
    tx_mod.recover_incomplete_transactions = MagicMock()
    tx_mod.summarize_transaction_health = MagicMock(return_value={})

    # ---- core.governance.prompts & gateway ----
    prompts_mod = _stub("core.governance.prompts")
    prompts_mod.QA_SYSTEM_PROMPT = "{context_blocks}"
    prompts_mod.build_context_block = lambda ctxs: str(ctxs)
    prompts_mod.STUDIO_PROMPTS = {t: "{context_blocks}" for t in
        ("summary", "faq", "briefing", "glossary", "action_items")}

    # ---- core.models ----
    _stub("core.models")
    src_model = _stub("core.models.source")

    class _SourceStatus:
        UPLOADING = "UPLOADING"
        PROCESSING = "PROCESSING"
        READY = "READY"
        FAILED = "FAILED"

    src_model.SourceStatus = _SourceStatus

    # ---- core.storage ----
    _stub("core.storage")
    nb_store_mod = _stub("core.storage.notebook_store")
    nb_store_mod.NotebookStore = MagicMock

    src_reg_mod = _stub("core.storage.source_registry")
    src_reg_mod.SourceRegistry = MagicMock

    note_store_mod = _stub("core.storage.note_store")
    note_store_mod.NoteStore = MagicMock

    chat_hist_mod = _stub("core.storage.chat_history_store")
    chat_hist_mod.ChatHistoryStore = MagicMock

    studio_store_mod = _stub("core.storage.studio_store")
    studio_store_mod.StudioStore = MagicMock

    graph_store_mod = _stub("core.storage.graph_store")
    graph_store_mod.GraphStore = MagicMock

    _stub("core.models.note")
    _stub("core.models.chat_message")
    so_mod = _stub("core.models.studio_output")
    class _StudioOutputType:
        @staticmethod
        def values():
            return ["summary", "faq", "briefing", "glossary", "action_items"]
    so_mod.StudioOutputType = _StudioOutputType

    _stub("core.models.graph")

    _stub("core.knowledge")
    graph_ext_mod = _stub("core.knowledge.graph_extractor")
    graph_ext_mod.GraphExtractor = MagicMock


class _FakeBM25IndexInstance:
    """Minimal BM25 instance for retriever tests: always empty."""
    size = 0
    def build(self, corpus): pass
    def query(self, query, top_k=10, extra_tokens=None): return []


class _FakeQueryExpanderInstance:
    """No-op query expander."""
    def expand(self, query):
        return query, []


def _make_retriever(vs: RecordingVectorStore):
    """Build a RetrieverEngine with all heavy sub-components replaced."""
    _install_stubs()
    from core.retrieval.retriever import RetrieverEngine  # noqa: PLC0415
    r = RetrieverEngine.__new__(RetrieverEngine)
    r.embedding_manager = FakeEmbeddingManager()
    r.vector_store = vs
    r.reranker = FakeReranker()
    r.bm25_index = _FakeBM25IndexInstance()
    r.query_expander = _FakeQueryExpanderInstance()
    return r


# ---------------------------------------------------------------------------
# Retriever-level isolation tests
# ---------------------------------------------------------------------------

def test_retriever_passes_source_ids_as_where_filter():
    """RetrieverEngine must translate source_ids into a Chroma $in filter."""
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)

    retriever.retrieve("any query", source_ids=["src-1", "src-2"])

    assert vs.last_where == {"source_id": {"$in": ["src-1", "src-2"]}}


def test_retriever_single_source_id_uses_eq_filter():
    """Single source_id should use $eq rather than $in for efficiency."""
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)

    retriever.retrieve("any query", source_ids=["src-1"])

    assert vs.last_where == {"source_id": {"$eq": "src-1"}}


def test_retriever_no_source_ids_passes_no_filter():
    """Without source_ids the where filter must be None (global search)."""
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)

    retriever.retrieve("any query", source_ids=None)

    assert vs.last_where is None


def test_notebook_a_cannot_retrieve_notebook_b_chunks():
    """
    Simulate Notebook A (src-1, src-2) and Notebook B (src-3).
    Retrieval for Notebook A must never surface chunks from src-3.
    """
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)

    results = retriever.retrieve("query", top_k=10, final_k=10, source_ids=["src-1", "src-2"])
    returned_source_ids = {r["metadata"]["source_id"] for r in results}

    assert "src-3" not in returned_source_ids
    assert returned_source_ids.issubset({"src-1", "src-2"})


def test_after_source_removal_source_id_absent_from_filter():
    """
    After source 2 is deleted from the registry its source_id must not
    appear in the where-filter used by the retriever.
    """
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)

    # Notebook A originally had src-1 and src-2; after deletion only src-1 remains
    active_source_ids = ["src-1"]
    retriever.retrieve("query", source_ids=active_source_ids)

    where = vs.last_where
    assert where is not None
    filter_val = where.get("source_id", {})
    present_ids = filter_val.get("$in") or [filter_val.get("$eq")]
    assert "src-2" not in present_ids


# ---------------------------------------------------------------------------
# API-level tests — FastAPI TestClient
# ---------------------------------------------------------------------------

def _import_api():
    """Import apps.api.main, using stub cache if already loaded."""
    _install_stubs()
    if "apps.api.main" not in sys.modules:
        import apps.api.main  # noqa: PLC0415
    return sys.modules["apps.api.main"]


def _build_app_with_fakes(notebook_sources_map: dict, llm_raises: bool = False):
    """
    Load the FastAPI app and replace shared singletons with fakes.
    Returns (app, RecordingVectorStore) so callers can inspect the filter.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    api_main = _import_api()

    # Mock notebook_store
    mock_nb_store = MagicMock()
    def get_nb(nid):
        if nid in notebook_sources_map:
            nb = MagicMock()
            nb.id = nid
            return nb
        return None
    mock_nb_store.get.side_effect = get_nb

    # Mock source_registry
    mock_src_reg = MagicMock()
    def list_sources(nid):
        srcs = []
        for sid in notebook_sources_map.get(nid, []):
            src = MagicMock()
            src.id = sid
            srcs.append(src)
        return srcs
    mock_src_reg.list_by_notebook.side_effect = list_sources

    # Retriever backed by RecordingVectorStore
    vs = RecordingVectorStore()
    retriever = _make_retriever(vs)
    mock_retriever = MagicMock()
    def do_retrieve(query, top_k, final_k, source_ids=None, notebook_id=None, **kwargs):
        return retriever.retrieve(query, top_k=top_k, final_k=final_k, source_ids=source_ids)
    mock_retriever.retrieve.side_effect = do_retrieve

    api_main.notebook_store = mock_nb_store
    api_main.source_registry = mock_src_reg
    api_main.retriever_engine = mock_retriever

    if llm_raises:
        api_main.invoke_local_llm = MagicMock(
            side_effect=api_main.LLMUnavailableError("vLLM not running")
        )
    else:
        api_main.invoke_local_llm = MagicMock(
            return_value="<citation src='doc1.pdf' page='1'>答案内容</citation>"
        )

    return api_main.app, vs


def test_chat_endpoint_scopes_to_notebook_sources():
    """
    POST /api/v1/chat with notebook_id='nb-a' must only retrieve from
    sources belonging to nb-a (src-1, src-2), not from src-3.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app, vs = _build_app_with_fakes(
        notebook_sources_map={"nb-a": ["src-1", "src-2"], "nb-b": ["src-3"]}
    )
    client = TestClient(app)

    resp = client.post("/api/v1/chat", json={"query": "test", "notebook_id": "nb-a"})

    assert vs.last_where is not None
    filter_ids = (
        vs.last_where["source_id"].get("$in")
        or [vs.last_where["source_id"].get("$eq")]
    )
    assert set(filter_ids) == {"src-1", "src-2"}
    assert "src-3" not in filter_ids


def test_chat_endpoint_returns_503_when_llm_unavailable():
    """
    When the local vLLM service is down the endpoint must return 503,
    not fall back to a mock response.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app, _ = _build_app_with_fakes(
        notebook_sources_map={"nb-a": ["src-1"]},
        llm_raises=True,
    )
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/v1/chat", json={"query": "test", "notebook_id": "nb-a"})

    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


def test_chat_endpoint_returns_400_for_unknown_notebook():
    """
    Requesting a chat for a notebook_id that does not exist must return 400.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app, _ = _build_app_with_fakes(notebook_sources_map={})
    client = TestClient(app)

    resp = client.post("/api/v1/chat", json={"query": "test", "notebook_id": "ghost-nb"})

    assert resp.status_code == 400


def test_chat_accepts_legacy_space_id_alias():
    """
    Legacy clients that send space_id instead of notebook_id must still work.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    app, vs = _build_app_with_fakes(
        notebook_sources_map={"legacy-space": ["src-1"]}
    )
    client = TestClient(app)

    resp = client.post("/api/v1/chat", json={"query": "test", "space_id": "legacy-space"})

    assert resp.status_code == 200
    assert vs.last_where is not None
