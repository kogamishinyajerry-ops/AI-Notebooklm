"""
test_graph.py
=============
S-23: Tests for Knowledge Graph / Mind Map Lite.

All heavy deps stubbed. Tests cover:
  * GraphExtractor entity/edge extraction
  * MindMap tree construction
  * GraphStore persistence roundtrip
  * API endpoints (generate, get)
"""
from __future__ import annotations

import sys
import types
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module stubs (same pattern as other test files)
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    for name in ("sentence_transformers", "chromadb", "fitz",
                 "transformers", "torch"):
        if name not in sys.modules:
            s = _stub(name)
            if name == "chromadb":
                cfg = _stub("chromadb.config")
                cfg.Settings = dict
                s.PersistentClient = MagicMock
                s.config = cfg
            elif name == "sentence_transformers":
                s.SentenceTransformer = MagicMock

    for name in [
        "core.retrieval.embeddings", "core.retrieval.reranker",
        "core.retrieval.vector_store", "core.retrieval.bm25_index",
        "core.retrieval.query_expander",
    ]:
        if name not in sys.modules:
            _stub(name)

    emb = sys.modules["core.retrieval.embeddings"]
    if not hasattr(emb, "EmbeddingManager"):
        emb.EmbeddingManager = MagicMock

    rer = sys.modules["core.retrieval.reranker"]
    if not hasattr(rer, "CrossEncoderReranker"):
        rer.CrossEncoderReranker = MagicMock

    vs = sys.modules["core.retrieval.vector_store"]
    if not hasattr(vs, "VectorStoreAdapter"):
        vs.VectorStoreAdapter = MagicMock

    bm25 = sys.modules["core.retrieval.bm25_index"]
    if not hasattr(bm25, "BM25Index"):
        bm25.BM25Index = MagicMock

    qe = sys.modules["core.retrieval.query_expander"]
    if not hasattr(qe, "QueryExpander"):
        qe.QueryExpander = MagicMock


_install_stubs()


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
                    "2026-04-18T00:00:00Z",
                    "2026-04-18T00:00:00Z",
                    0,
                    None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REAL_MODULES_TO_EVICT = (
    "core.storage.graph_store",
    "core.models.graph",
    "core.knowledge.graph_extractor",
    "core.knowledge",
    "core.storage",
    "core.models",
)

# Retrieval stubs that test_graph._install_stubs() plants — must be evicted
# after each test so test_retrieval_quality / test_retriever get real modules.
_RETRIEVAL_STUB_MODULES = (
    "core.retrieval.bm25_index",
    "core.retrieval.query_expander",
)


@pytest.fixture(autouse=True)
def _evict_graph_stubs(tmp_path):
    saved = {}
    for mod in _REAL_MODULES_TO_EVICT:
        if mod in sys.modules:
            saved[mod] = sys.modules.pop(mod)
    _seed_notebooks(
        tmp_path / "notebooks.db",
        ("nb-1", "nb-x", "nb-del", "nb-rt", "nb-test"),
    )
    yield
    # Restore real modules
    sys.modules.update(saved)
    # Always evict the retrieval stub modules planted by _install_stubs()
    # so subsequent test files (test_retrieval_quality, test_retriever) get
    # fresh real imports of bm25_index and query_expander.
    for mod in _RETRIEVAL_STUB_MODULES:
        sys.modules.pop(mod, None)
    # Also evict the retriever itself so it reimports with real sub-deps
    sys.modules.pop("core.retrieval.retriever", None)


# ---------------------------------------------------------------------------
# Sample corpus
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = [
    {
        "text": "CFD analysis of C919 wing aerodynamics. The boundary layer separation near the leading edge affects the lift coefficient.",
        "metadata": {"source_id": "s1", "page": "1"},
    },
    {
        "text": "RANS turbulence model applied to the C919 airfoil. Reynolds number effects on the mesh convergence residual.",
        "metadata": {"source_id": "s1", "page": "2"},
    },
    {
        "text": "C919 elevator trim authority analysis. The pitching moment Cm shows nonlinear behaviour at high angle of attack.",
        "metadata": {"source_id": "s1", "page": "3"},
    },
    {
        "text": "Boundary layer transition to turbulence on the wing surface. CFD mesh refinement improves convergence.",
        "metadata": {"source_id": "s1", "page": "4"},
    },
    {
        "text": "升降舵是飞机纵向配平的关键部件。失速特性分析需要考虑边界层分离效应。",
        "metadata": {"source_id": "s1", "page": "5"},
    },
]


# ===========================================================================
# GraphExtractor tests
# ===========================================================================

class TestGraphExtractor:
    def test_extract_nodes_from_chunks(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)

        labels = {n.label for n in graph.nodes}
        # CFD appears in multiple chunks → must be a node
        assert "CFD" in labels

    def test_extract_edges_co_occurrence(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        # Two terms appearing in the same chunk must produce a co-occurrence edge
        chunks = [
            {"text": "CFD mesh convergence residual analysis", "metadata": {"source_id": "s1"}},
            {"text": "CFD mesh convergence residual analysis", "metadata": {"source_id": "s1"}},
            {"text": "CFD mesh convergence residual analysis", "metadata": {"source_id": "s1"}},
        ]
        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(chunks)
        # There must be at least one edge
        assert len(graph.edges) >= 1

    def test_chinese_entities_extracted(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        chunks = [
            {"text": "升降舵是飞机配平系统的核心部件", "metadata": {"source_id": "s1"}},
            {"text": "升降舵偏角影响俯仰力矩", "metadata": {"source_id": "s1"}},
        ]
        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(chunks)
        labels = {n.label for n in graph.nodes}
        assert "升降舵" in labels

    def test_node_weights_normalised(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)
        for node in graph.nodes:
            assert 0.0 <= node.weight <= 1.0

    def test_empty_chunks_returns_empty_graph(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor()
        graph = extractor.extract([])
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.mindmap is None

    def test_generated_at_is_set(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)
        assert graph.generated_at != ""


# ===========================================================================
# MindMap tree tests
# ===========================================================================

class TestMindMapTree:
    def test_mindmap_root_is_highest_weight_node(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)

        if graph.mindmap is None:
            pytest.skip("not enough entities for mindmap")

        root_id = graph.mindmap.id
        root_node = next((n for n in graph.nodes if n.id == root_id), None)
        assert root_node is not None

        max_weight = max(n.weight for n in graph.nodes)
        # Root's weight should be the maximum (within floating point tolerance)
        assert abs(root_node.weight - max_weight) < 1e-6

    def test_mindmap_max_depth_3(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)

        if graph.mindmap is None:
            pytest.skip("not enough entities for mindmap")

        def _max_depth(node, d=0):
            if not node.children:
                return d
            return max(_max_depth(c, d + 1) for c in node.children)

        assert _max_depth(graph.mindmap) <= 3

    def test_mindmap_serialise_roundtrip(self):
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415
        from core.models.graph import MindMapNode  # noqa: PLC0415

        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)

        if graph.mindmap is None:
            pytest.skip("no mindmap generated")

        d = graph.mindmap.to_dict()
        restored = MindMapNode.from_dict(d)
        assert restored.id == graph.mindmap.id
        assert restored.label == graph.mindmap.label


# ===========================================================================
# GraphStore tests
# ===========================================================================

class TestGraphStore:
    def test_persist_and_load(self, tmp_path):
        from core.storage.graph_store import GraphStore  # noqa: PLC0415
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        store = GraphStore(db_path=tmp_path / "notebooks.db")
        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)

        store.save("nb-1", graph)
        loaded = store.load("nb-1")

        assert loaded is not None
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)

    def test_load_missing_returns_none(self, tmp_path):
        from core.storage.graph_store import GraphStore  # noqa: PLC0415

        store = GraphStore(db_path=tmp_path / "notebooks.db")
        assert store.load("no-such-notebook") is None

    def test_exists(self, tmp_path):
        from core.storage.graph_store import GraphStore  # noqa: PLC0415
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        store = GraphStore(db_path=tmp_path / "notebooks.db")
        assert not store.exists("nb-x")
        extractor = GraphExtractor(min_freq=1)
        graph = extractor.extract(SAMPLE_CHUNKS)
        store.save("nb-x", graph)
        assert store.exists("nb-x")

    def test_delete(self, tmp_path):
        from core.storage.graph_store import GraphStore  # noqa: PLC0415
        from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415

        store = GraphStore(db_path=tmp_path / "notebooks.db")
        extractor = GraphExtractor(min_freq=1)
        store.save("nb-del", extractor.extract(SAMPLE_CHUNKS))
        assert store.delete("nb-del") is True
        assert not store.exists("nb-del")
        assert store.delete("nb-del") is False


# ===========================================================================
# API endpoint tests
# ===========================================================================

def _install_api_stubs(tmp_path: Path):
    """Install all stubs needed for main.py to import cleanly."""
    _install_stubs()

    def _ensure_stub(name):
        if name not in sys.modules:
            return _stub(name)
        return sys.modules[name]

    # services.ingestion
    for name in [
        "services", "services.ingestion", "services.ingestion.service",
        "services.ingestion.filenames", "services.ingestion.chunker",
        "services.ingestion.parser",
    ]:
        _ensure_stub(name)
    sys.modules["services.ingestion.service"].IngestionService = MagicMock
    sys.modules["services.ingestion.filenames"].safe_upload_path = MagicMock
    sys.modules["services.ingestion.filenames"].validate_pdf_magic = MagicMock

    # core.ingestion.transaction
    for name in ["core.ingestion", "core.ingestion.transaction"]:
        _ensure_stub(name)
    txn = sys.modules["core.ingestion.transaction"]
    for attr in ["IngestTransaction", "cleanup_committed_transactions",
                 "iter_space_ids", "recover_incomplete_transactions",
                 "summarize_transaction_health"]:
        if not hasattr(txn, attr):
            setattr(txn, attr, MagicMock())
    txn.iter_space_ids.return_value = []

    # core.retrieval
    retriever_mod = _ensure_stub("core.retrieval.retriever")

    class _FakeEmbedding:
        def tolist(self):
            return [0.1, 0.2, 0.3]

    class _FakeRetriever:
        def retrieve(self, query, top_k=10, final_k=3, source_ids=None, **kwargs):
            return SAMPLE_CHUNKS[:final_k]

    retriever_mod.RetrieverEngine = _FakeRetriever

    # core.governance
    for name in ["core.governance", "core.governance.prompts", "core.governance.gateway"]:
        _ensure_stub(name)
    prompts = sys.modules["core.governance.prompts"]
    if not hasattr(prompts, "QA_SYSTEM_PROMPT"):
        prompts.QA_SYSTEM_PROMPT = "system prompt"
    if not hasattr(prompts, "build_context_block"):
        prompts.build_context_block = lambda chunks: "context"
    if not hasattr(prompts, "STUDIO_PROMPTS"):
        prompts.STUDIO_PROMPTS = {t: "{context_blocks}" for t in
            ("summary", "faq", "briefing", "glossary", "action_items")}

    gw_mod = sys.modules["core.governance.gateway"]

    class _FakeGateway:
        @staticmethod
        def validate_and_parse(response, contexts):
            return True, response, []

    gw_mod.AntiHallucinationGateway = _FakeGateway

    # core.models
    for name in ["core.models.source", "core.models.studio_output"]:
        _ensure_stub(name)
    sys.modules["core.models.source"].SourceStatus = type(
        "SourceStatus", (), {"READY": "ready"})

    class _StudioOutputType:
        @staticmethod
        def values():
            return ["summary", "faq", "briefing", "glossary", "action_items"]

    sys.modules["core.models.studio_output"].StudioOutputType = _StudioOutputType

    # core.storage — use real implementations for notebook/source/note/chat/studio/graph
    for name in [
        "core.storage.notebook_store", "core.storage.source_registry",
        "core.storage.note_store", "core.storage.chat_history_store",
        "core.storage.studio_store",
    ]:
        if name in sys.modules:
            sys.modules.pop(name)

    # stub StudioStore/NoteStore/etc as MagicMock since we test Graph specifically
    for name in [
        "core.storage.notebook_store", "core.storage.source_registry",
        "core.storage.note_store", "core.storage.chat_history_store",
        "core.storage.studio_store",
    ]:
        mod = _stub(name)
        class_name = name.split(".")[-1]
        parts = class_name.split("_")
        cls_name = "".join(p.title() for p in parts)
        setattr(mod, cls_name, MagicMock)

    # core.knowledge / graph_extractor / graph_store — use REAL modules
    for name in [
        "core.knowledge", "core.knowledge.graph_extractor",
        "core.storage.graph_store", "core.models.graph",
    ]:
        if name in sys.modules:
            sys.modules.pop(name)


def _get_app(tmp_path: Path):
    _install_api_stubs(tmp_path)

    # Pop apps.api.main so it reimports fresh
    for name in list(sys.modules.keys()):
        if "apps.api" in name:
            sys.modules.pop(name)

    import apps.api.main as main_mod  # noqa: PLC0415

    # Wire real GraphStore + GraphExtractor to use tmp_path
    from core.storage.graph_store import GraphStore  # noqa: PLC0415
    from core.knowledge.graph_extractor import GraphExtractor  # noqa: PLC0415
    main_mod.graph_store = GraphStore(db_path=tmp_path / "notebooks.db")
    main_mod.graph_extractor = GraphExtractor(min_freq=1)

    # Wire notebook_store so notebook_id lookups work
    class _FakeNotebookStore:
        def get(self, nb_id):
            if nb_id == "nb-test":
                return object()
            return None
        def update(self, *a, **kw): pass

    main_mod.notebook_store = _FakeNotebookStore()

    # Wire source_registry so sources are found
    class _FakeSource:
        def __init__(self, sid):
            self.id = sid
            self.status = "ready"

    class _FakeSourceRegistry:
        def list_by_notebook(self, nb_id):
            return [_FakeSource("src-1")]
        def get(self, nb_id, src_id): return _FakeSource(src_id)
        @property
        def spaces_dir(self): return tmp_path

    main_mod.source_registry = _FakeSourceRegistry()

    return main_mod.app


class TestGraphAPI:
    def test_api_generate_returns_201(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        app = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/nb-test/graph/generate")
        assert resp.status_code == 201
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert "mindmap" in data
        assert "generated_at" in data

    def test_api_generate_404_unknown_notebook(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        app = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.post("/api/v1/notebooks/unknown-nb/graph/generate")
        assert resp.status_code == 404

    def test_api_generate_422_no_sources(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        # Build a fresh app with an empty source registry so the 422 path is hit
        app = _get_app(tmp_path)
        import apps.api.main as main_mod  # noqa: PLC0415

        class _EmptySourceRegistry:
            def list_by_notebook(self, nb_id): return []
            def get(self, nb_id, src_id): return None
            @property
            def spaces_dir(self): return tmp_path

        # Replace on the already-imported module — FastAPI routes capture the
        # module-global name at call time, so this works.
        original = main_mod.source_registry
        main_mod.source_registry = _EmptySourceRegistry()
        try:
            client = TestClient(app)
            resp = client.post("/api/v1/notebooks/nb-test/graph/generate")
            assert resp.status_code == 422
        finally:
            main_mod.source_registry = original

    def test_api_get_graph_404_not_generated(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        app = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.get("/api/v1/notebooks/nb-test/graph")
        assert resp.status_code == 404

    def test_api_get_graph_returns_cached(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        app = _get_app(tmp_path)
        client = TestClient(app)

        # Generate first
        gen = client.post("/api/v1/notebooks/nb-test/graph/generate")
        assert gen.status_code == 201

        # Then GET should return it
        get = client.get("/api/v1/notebooks/nb-test/graph")
        assert get.status_code == 200
        assert "nodes" in get.json()

    def test_api_graph_404_unknown_notebook_on_get(self, tmp_path):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        app = _get_app(tmp_path)
        client = TestClient(app)
        resp = client.get("/api/v1/notebooks/unknown/graph")
        assert resp.status_code == 404


# ===========================================================================
# Gap-A: GraphStore.get_neighbors / get_source_chunks tests
# ===========================================================================

class TestGraphStoreGapA:
    """Tests for the two new Gap-A retrieval helpers on GraphStore."""

    def _make_graph(self, tmp_path):
        """Build and persist a simple 3-node knowledge graph."""
        from core.models.graph import GraphNode, GraphEdge, KnowledgeGraph  # noqa: PLC0415
        from core.storage.graph_store import GraphStore  # noqa: PLC0415

        nodes = [
            GraphNode(id="cfd", label="CFD", weight=1.0, lang="en",
                      chunk_ids=["chunk-1", "chunk-2"]),
            GraphNode(id="boundary_layer", label="boundary layer", weight=0.8,
                      lang="en", chunk_ids=["chunk-1"]),
            GraphNode(id="mesh", label="mesh", weight=0.6, lang="en",
                      chunk_ids=["chunk-3"]),
        ]
        edges = [
            GraphEdge(source="cfd", target="boundary_layer",
                      relation="co-occurrence", weight=0.9),
            GraphEdge(source="cfd", target="mesh",
                      relation="co-occurrence", weight=0.7),
        ]
        kg = KnowledgeGraph(nodes=nodes, edges=edges, generated_at="2026-01-01T00:00:00Z")

        gs = GraphStore(db_path=tmp_path / "notebooks.db")
        gs.save("nb-1", kg)
        return gs

    def test_get_neighbors_direct(self, tmp_path):
        """CFD has two direct neighbours: boundary layer and mesh."""
        gs = self._make_graph(tmp_path)
        neighbours = gs.get_neighbors("nb-1", "CFD", depth=1)
        assert set(neighbours) == {"boundary layer", "mesh"}

    def test_get_neighbors_depth_zero_returns_empty(self, tmp_path):
        """Depth 0 means no traversal — returns no neighbours."""
        gs = self._make_graph(tmp_path)
        neighbours = gs.get_neighbors("nb-1", "CFD", depth=0)
        assert neighbours == []

    def test_get_neighbors_unknown_entity(self, tmp_path):
        """Entity not in the graph → empty list."""
        gs = self._make_graph(tmp_path)
        neighbours = gs.get_neighbors("nb-1", "NONEXISTENT", depth=1)
        assert neighbours == []

    def test_get_neighbors_no_graph(self, tmp_path):
        """No graph stored → empty list (graceful degradation)."""
        from core.storage.graph_store import GraphStore  # noqa: PLC0415
        gs = GraphStore(db_path=tmp_path / "notebooks.db")
        assert gs.get_neighbors("missing-nb", "CFD", depth=1) == []

    def test_get_source_chunks_known_entity(self, tmp_path):
        """CFD is reverse-indexed to chunk-1 and chunk-2."""
        gs = self._make_graph(tmp_path)
        chunks = gs.get_source_chunks("nb-1", "CFD")
        assert chunks == ["chunk-1", "chunk-2"]

    def test_get_source_chunks_unknown_entity(self, tmp_path):
        """Entity not present in graph → empty list."""
        gs = self._make_graph(tmp_path)
        assert gs.get_source_chunks("nb-1", "UNKNOWN") == []

    def test_get_source_chunks_no_graph(self, tmp_path):
        """No graph persisted → empty list."""
        from core.storage.graph_store import GraphStore  # noqa: PLC0415
        gs = GraphStore(db_path=tmp_path / "notebooks.db")
        assert gs.get_source_chunks("missing-nb", "CFD") == []

    def test_chunk_ids_preserved_in_roundtrip(self, tmp_path):
        """chunk_ids must survive save/load JSON roundtrip."""
        from core.models.graph import GraphNode, KnowledgeGraph  # noqa: PLC0415
        from core.storage.graph_store import GraphStore  # noqa: PLC0415

        gs = GraphStore(db_path=tmp_path / "notebooks.db")
        kg = KnowledgeGraph(nodes=[
            GraphNode(id="rans", label="RANS", weight=0.9, lang="en",
                      chunk_ids=["x", "y", "z"])
        ])
        gs.save("nb-rt", kg)
        loaded = gs.load("nb-rt")
        assert loaded.nodes[0].chunk_ids == ["x", "y", "z"]
