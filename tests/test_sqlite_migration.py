"""
test_sqlite_migration.py
========================
Tests for the V4.1-T2 JSON → SQLite storage migration.

Covers:
  * migrate_from_json() correctly migrates all 5 store types
  * run_migration_if_needed() skips when already migrated
  * Idempotent: re-running migration on already-migrated data is a no-op
  * Corrupted/missing JSON files are handled gracefully
  * Stores work correctly against migrated SQLite DB
  * WAL mode and schema are correctly configured

No heavy ML dependencies — runs fully offline.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub heavy dependencies so migration can run without chromadb/sentence_transformers
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


@pytest.fixture(autouse=True)
def _stub_heavy_deps():
    """Stub chromadb, sentence_transformers, and torch before migration tests.

    NOTE: We deliberately do NOT permanently stub core.storage (a namespace
    package). Stubbing it replaces the namespace with a regular ModuleType,
    which breaks submodule resolution (core.storage.sqlite_db can't be found).
    Instead, we evict it from sys.modules after stubbing so Python recreates it
    as a namespace package when re-imported.
    """
    for name in ("chromadb", "sentence_transformers", "torch", "transformers"):
        if name not in sys.modules:
            _stub(name)
    yield
    # Restore: evict stubbed modules so real ones are re-imported by subsequent tests
    for name in list(sys.modules.keys()):
        if name in ("chromadb", "sentence_transformers", "torch",
                    "transformers", "core.storage"):
            del sys.modules[name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _utc_now() -> str:
    return "2025-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _import_sqlite_db(tmp_path):
    """Return the sqlite_db module functions, freshly imported.

    The _stub_heavy_deps fixture runs first and may have replaced core.storage
    (a namespace package) with a regular ModuleType stub.  We must delete that
    stub from sys.modules before importing sqlite_db, otherwise Python cannot
    resolve the sqlite_db submodule.

    Additionally, test_llm_health.py stubs core.models.source (only SourceStatus,
    not Source), which persists to test_sqlite_migration.py. We evict it and
    reload source_registry so it picks up the real Source class.
    """
    import importlib

    # Evict the core.storage stub so Python recreates it as a namespace package
    sys.modules.pop("core.storage", None)
    for _k in list(sys.modules.keys()):
        if _k.startswith("core.storage."):
            sys.modules.pop(_k, None)

    # Evict core.models stubs (created by test_llm_health.py and
    # test_cross_notebook_isolation.py) so that storage modules can import the
    # real classes.  These stubs only define minimal types (e.g. SourceStatus,
    # StudioOutputType) but not the full classes (Source, StudioOutput).
    for _mod in (
        "core.models.source",
        "core.models.note",
        "core.models.chat_message",
        "core.models.studio_output",
        "core.models.graph",
        "core.models",
    ):
        sys.modules.pop(_mod, None)

    # Evict storage modules that may have cached the Source import from the stub.
    # CRITICAL: Also evict source_registry itself so it is re-imported with the
    # real Source (not Source=None from the stub).
    for _k in list(sys.modules.keys()):
        if _k.startswith("core.storage."):
            sys.modules.pop(_k, None)

    # Stub core.ingestion.transaction so migration can import it
    tx_mod = types.ModuleType("core.ingestion.transaction")
    tx_mod.DEFAULT_SPACES_DIR = tmp_path / "spaces"
    tx_mod.iter_space_ids = MagicMock(return_value=[])
    tx_mod.utc_now_iso = _utc_now
    sys.modules["core.ingestion.transaction"] = tx_mod

    import core.storage.sqlite_db as sqlite_db
    importlib.reload(sqlite_db)

    # Re-import source_registry so it picks up the real Source.
    # First, force the real core.models modules into sys.modules so that
    # source_registry.py's "from core.models.source import Source" finds them.
    if "core.storage.source_registry" in sys.modules:
        del sys.modules["core.storage.source_registry"]
    # Re-import the real core.models.source BEFORE source_registry runs its
    # module-level import of Source.  This guarantees Source is available.
    for _mod in ("core.models", "core.models.source"):
        sys.modules.pop(_mod, None)
    importlib.import_module("core.models.source")   # bring real Source into scope
    importlib.import_module("core.storage.source_registry")

    return sqlite_db


# ---------------------------------------------------------------------------
# Migration correctness
# ---------------------------------------------------------------------------

def test_migrate_notebooks(tmp_path, _import_sqlite_db):
    """notebooks.json is migrated to SQLite notebooks table."""
    sqlite_db = _import_sqlite_db

    # Create JSON store
    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"

    nb_id = "nb-test-001"
    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id,
            "name": "Test Notebook",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "source_count": 2,
            "owner_id": "user-1",
        }
    ])

    # Create a minimal space directory
    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    _write_json(nb_dir / "sources.json", [])
    _write_json(nb_dir / "notes.json", [])
    _write_json(nb_dir / "chat_history.json", [])
    _write_json(nb_dir / "studio.json", [])
    _write_json(nb_dir / "graph.json", {})

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    assert result.success is True
    assert result.version == 1
    assert result.counts.get("notebooks") == 1

    # Verify SQLite data
    conn = sqlite_db.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM notebooks WHERE id = ?", (nb_id,)
    ).fetchone()
    assert row is not None
    assert row["name"] == "Test Notebook"
    assert row["source_count"] == 2
    assert row["owner_id"] == "user-1"
    conn.close()


def test_migrate_notes_and_sources(tmp_path, _import_sqlite_db):
    """Per-notebook notes.json and sources.json are migrated."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"
    nb_id = "nb-test-002"

    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "NB2",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)

    _write_json(nb_dir / "notes.json", [
        {
            "id": "note-1", "title": "First Note",
            "content": "Hello world",
            "citations": [{"text": "src", "page": 1}],
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])
    _write_json(nb_dir / "sources.json", [
        {
            "id": "src-1",
            "filename": "doc.pdf",
            "file_path": str(nb_dir / "doc.pdf"),
            "status": "ready",
            "page_count": 10,
            "chunk_count": 50,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])
    _write_json(nb_dir / "chat_history.json", [])
    _write_json(nb_dir / "studio.json", [])
    _write_json(nb_dir / "graph.json", {})

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    assert result.success is True
    assert result.counts.get("notes") == 1
    assert result.counts.get("sources") == 1

    conn = sqlite_db.get_connection(db_path)
    note_row = conn.execute(
        "SELECT * FROM notes WHERE id = ?", ("note-1",)
    ).fetchone()
    assert note_row["title"] == "First Note"
    src_row = conn.execute(
        "SELECT * FROM sources WHERE id = ?", ("src-1",)
    ).fetchone()
    assert src_row["filename"] == "doc.pdf"
    assert src_row["status"] == "ready"
    conn.close()


def test_migrate_chat_history_and_studio(tmp_path, _import_sqlite_db):
    """chat_history.json and studio.json are migrated."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"
    nb_id = "nb-test-003"

    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "NB3",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    _write_json(nb_dir / "notes.json", [])
    _write_json(nb_dir / "sources.json", [])
    _write_json(nb_dir / "chat_history.json", [
        {
            "id": "msg-1",
            "role": "user",
            "content": "What is lift?",
            "is_fully_verified": True,
            "created_at": "2025-01-01T00:00:00Z",
        },
        {
            "id": "msg-2",
            "role": "assistant",
            "content": "Lift is aerodynamic force.",
            "is_fully_verified": False,
            "created_at": "2025-01-01T00:01:00Z",
        },
    ])
    _write_json(nb_dir / "studio.json", [
        {
            "id": "out-1",
            "output_type": "summary",
            "title": "Brief Summary",
            "content": "This document covers aerodynamic principles.",
            "created_at": "2025-01-01T00:00:00Z",
        }
    ])
    _write_json(nb_dir / "graph.json", {})

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    assert result.success is True
    assert result.counts.get("chat_messages") == 2
    assert result.counts.get("studio_outputs") == 1

    conn = sqlite_db.get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE notebook_id = ? ORDER BY created_at",
        (nb_id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[1]["role"] == "assistant"

    studio_row = conn.execute(
        "SELECT * FROM studio_outputs WHERE id = ?", ("out-1",)
    ).fetchone()
    assert studio_row["output_type"] == "summary"
    conn.close()


def test_migrate_graph(tmp_path, _import_sqlite_db):
    """graph.json is migrated to knowledge_graphs table."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"
    nb_id = "nb-graph-001"

    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "Graph NB",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    _write_json(nb_dir / "notes.json", [])
    _write_json(nb_dir / "sources.json", [])
    _write_json(nb_dir / "chat_history.json", [])
    _write_json(nb_dir / "studio.json", [])
    _write_json(nb_dir / "graph.json", {
        "nodes": [
            {"id": "n1", "label": "Lift", "chunk_ids": ["c1"], "weight": 0.8}
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n1", "relation": "self"}
        ],
        "mindmap": {"root": "n1", "children": []},
        "generated_at": "2025-01-01T12:00:00Z",
        "updated_at": "2025-01-01T12:00:00Z",
    })

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    assert result.success is True
    assert result.counts.get("knowledge_graphs") == 1

    conn = sqlite_db.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM knowledge_graphs WHERE notebook_id = ?", (nb_id,)
    ).fetchone()
    assert row is not None
    nodes = json.loads(row["nodes"])
    assert len(nodes) == 1
    assert nodes[0]["label"] == "Lift"
    conn.close()


def test_migration_is_idempotent(tmp_path, _import_sqlite_db):
    """Re-running migration on already-migrated data is a no-op."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"

    nb_id = "nb-idempotent"

    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "Idempotent NB",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    for fname in ("notes.json", "sources.json", "chat_history.json", "studio.json", "graph.json"):
        _write_json(nb_dir / fname, [] if fname != "graph.json" else {})

    # First migration
    result1 = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )
    assert result1.success is True
    assert result1.counts.get("notebooks") == 1

    # Second migration — should skip (already migrated)
    result2 = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )
    assert result2.success is True
    assert result2.counts == {}  # No records re-inserted


def test_no_json_files_is_noop(tmp_path, _import_sqlite_db):
    """When notebooks.json doesn't exist, migration returns immediately."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"
    data_dir.mkdir(parents=True)  # No notebooks.json

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    # Should succeed but migrate 0 records
    assert result.success is True
    # _insert_notebooks is called with [] so counts reflects notebooks: 0
    assert result.counts.get("notebooks", 0) == 0

    # Schema should still be initialized
    conn = sqlite_db.get_connection(db_path)
    version = sqlite_db.get_schema_version(conn)
    assert version == 1  # schema_version row exists
    conn.close()


def test_run_migration_if_needed_no_json(tmp_path, _import_sqlite_db):
    """run_migration_if_needed skips when already migrated."""
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"

    # Pre-create DB with schema version (already migrated)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    sqlite_db.set_schema_version(conn, version=1)
    conn.close()

    result = sqlite_db.run_migration_if_needed(
        base_dir=data_dir,
        db_path=db_path,
        spaces_dir=spaces_dir,
    )

    assert result.success is True
    assert result.version == 1
    assert result.counts == {}


def test_corrupted_json_causes_migration_failure(tmp_path, _import_sqlite_db):
    """Malformed JSON in a per-notebook file causes full migration rollback.

    Current behavior: _insert_* functions call json.loads() directly, so corrupted
    JSON raises json.JSONDecodeError which propagates and causes full rollback.
    This is conservative - it prevents partial migrations.
    """
    sqlite_db = _import_sqlite_db

    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"
    db_path = data_dir / "notebooks.db"
    nb_id = "nb-partial"

    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "Partial NB",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    # Write CORRUPTED JSON for notes
    (nb_dir / "notes.json").write_text("{ invalid json", encoding="utf-8")
    _write_json(nb_dir / "sources.json", [])
    _write_json(nb_dir / "chat_history.json", [])
    _write_json(nb_dir / "studio.json", [])
    _write_json(nb_dir / "graph.json", {})

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )

    # Full failure: JSON decode error propagates and causes rollback
    assert result.success is False
    assert len(result.errors) > 0
    # notebooks.json should NOT have been migrated (full rollback)
    conn = sqlite_db.get_connection(db_path)
    row = conn.execute("SELECT COUNT(*) as c FROM notebooks").fetchone()
    assert row["c"] == 0
    conn.close()


def test_wal_mode_enabled(tmp_path, _import_sqlite_db):
    """SQLite connection uses WAL journal mode."""
    sqlite_db = _import_sqlite_db

    db_path = tmp_path / "test.db"
    conn = sqlite_db.get_connection(db_path)

    # Check WAL mode
    result = conn.execute("PRAGMA journal_mode").fetchone()[0].upper()
    assert result == "WAL"

    # Check FK enforcement
    fk_result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_result == 1

    conn.close()


def test_stores_work_after_migration(tmp_path, _import_sqlite_db):
    """All 6 stores can read/write against migrated SQLite DB."""
    sqlite_db = _import_sqlite_db

    db_path = tmp_path / "notebooks.db"
    data_dir = tmp_path / "data"
    spaces_dir = tmp_path / "spaces"

    nb_id = "nb-stores-001"
    notebooks_json = data_dir / "notebooks.json"
    _write_json(notebooks_json, [
        {
            "id": nb_id, "name": "Stores Test NB",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
    ])

    nb_dir = spaces_dir / nb_id
    nb_dir.mkdir(parents=True)
    for fname in ("notes.json", "sources.json", "chat_history.json", "studio.json", "graph.json"):
        _write_json(nb_dir / fname, [] if fname != "graph.json" else {})

    result = sqlite_db.migrate_from_json(
        db_path=db_path,
        base_dir=data_dir,
        spaces_dir=spaces_dir,
    )
    assert result.success is True

    # Now test each store
    from core.storage.notebook_store import NotebookStore
    from core.storage.note_store import NoteStore
    from core.storage.source_registry import SourceRegistry
    from core.storage.chat_history_store import ChatHistoryStore
    from core.storage.studio_store import StudioStore
    from core.storage.graph_store import GraphStore

    ns = NotebookStore(db_path=db_path)
    nb = ns.create(name="After Migration NB")
    assert nb.name == "After Migration NB"
    assert ns.get(nb.id).name == "After Migration NB"

    nstore = NoteStore(db_path=db_path)
    note = nstore.create(nb.id, content="Note content here", citations=[],
                         title="Post-Migration Note")
    assert nstore.get(nb.id, note.id).title == "Post-Migration Note"

    reg = SourceRegistry(db_path=db_path)
    src = reg.register(nb.id, filename="test.pdf", file_path=str(nb_dir / "test.pdf"))
    assert reg.list_by_notebook(nb.id)[0].id == src.id

    chat_store = ChatHistoryStore(db_path=db_path)
    msg = chat_store.append(nb.id, role="user", content="Hello after migration")
    assert chat_store.list_by_notebook(nb.id)[0].content == "Hello after migration"

    studio = StudioStore(db_path=db_path)
    out = studio.create(nb.id, output_type="summary", content="Summary content",
                        citations=[], title="Summary")
    assert studio.get(nb.id, out.id).title == "Summary"

    graph = GraphStore(db_path=db_path)
    from core.models.graph import KnowledgeGraph, GraphNode
    kg = KnowledgeGraph(
        nodes=[GraphNode(id="n1", label="TestEntity", chunk_ids=[], weight=1.0)],
        edges=[],
        generated_at="2025-01-01T00:00:00Z",
    )
    graph.save(nb.id, kg)
    loaded = graph.load(nb.id)
    assert loaded is not None
    assert len(loaded.nodes) == 1
    assert loaded.nodes[0].label == "TestEntity"


def test_schema_tables_exist(tmp_path, _import_sqlite_db):
    """All 6 tables and their indexes are created by init_schema."""
    sqlite_db = _import_sqlite_db

    db_path = tmp_path / "schema_test.db"
    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)

    tables = [
        "notebooks", "notes", "sources",
        "chat_messages", "studio_outputs", "knowledge_graphs",
        "schema_version",
    ]
    for table in tables:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        assert result is not None, f"Table {table} not found"

    # Verify indexes
    indexes = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    assert "idx_notes_notebook" in indexes
    assert "idx_sources_notebook" in indexes
    assert "idx_chat_notebook_created" in indexes
    assert "idx_studio_notebook" in indexes

    conn.close()
