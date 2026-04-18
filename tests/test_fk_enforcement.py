from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _minimal_graph():
    from core.models.graph import GraphNode, KnowledgeGraph

    return KnowledgeGraph(
        nodes=[
            GraphNode(
                id="cfd",
                label="CFD",
                weight=1.0,
                lang="en",
                chunk_ids=["chunk-1"],
            )
        ],
        edges=[],
        generated_at="2026-04-18T00:00:00+00:00",
    )


def _insert_notebook(conn, notebook_id: str) -> None:
    conn.execute(
        """
        INSERT INTO notebooks (id, name, created_at, updated_at, source_count, owner_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            notebook_id,
            f"Notebook {notebook_id}",
            "2026-04-18T00:00:00+00:00",
            "2026-04-18T00:00:00+00:00",
            0,
            None,
        ),
    )


def _insert_orphan_note(conn, note_id: str = "orphan-note", notebook_id: str = "ghost") -> None:
    conn.execute(
        """
        INSERT INTO notes (id, notebook_id, title, content, citations, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            note_id,
            notebook_id,
            "Orphan",
            "content",
            "[]",
            "2026-04-18T00:00:00+00:00",
            "2026-04-18T00:00:00+00:00",
        ),
    )


def _insert_orphan_graph(conn, notebook_id: str = "ghost-graph") -> None:
    conn.execute(
        """
        INSERT INTO knowledge_graphs
            (notebook_id, nodes, edges, mindmap, generated_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            notebook_id,
            "[]",
            "[]",
            None,
            "2026-04-18T00:00:00+00:00",
            "2026-04-18T00:00:00+00:00",
        ),
    )


@pytest.fixture(autouse=True)
def _stub_transaction_module(tmp_path):
    for name in list(sys.modules):
        if name == "core.storage" or name.startswith("core.storage."):
            sys.modules.pop(name, None)
        if name == "core.models" or name.startswith("core.models."):
            sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)
    transaction_mod = types.ModuleType("core.ingestion.transaction")
    transaction_mod.DEFAULT_SPACES_DIR = tmp_path / "spaces"
    transaction_mod.iter_space_ids = MagicMock(return_value=[])
    transaction_mod.utc_now_iso = lambda: "2026-04-18T00:00:00+00:00"
    sys.modules["core.ingestion.transaction"] = transaction_mod
    yield
    for name in list(sys.modules):
        if name == "core.storage" or name.startswith("core.storage."):
            sys.modules.pop(name, None)
        if name == "core.models" or name.startswith("core.models."):
            sys.modules.pop(name, None)
    sys.modules.pop("core.ingestion.transaction", None)


@pytest.fixture
def _import_sqlite_db():
    sys.modules.pop("core.storage.sqlite_db", None)
    sys.modules.pop("core.storage.migrations", None)
    sys.modules.pop("core.storage.migrations.v4_2_t5_fk_enforcement", None)
    import core.storage.sqlite_db as sqlite_db

    return importlib.reload(sqlite_db)


def test_migration_user_version_bumped(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_foreign_keys_pragma_enabled_on_every_connection(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    conn.close()

    from core.storage.chat_history_store import ChatHistoryStore
    from core.storage.graph_store import GraphStore
    from core.storage.note_store import NoteStore
    from core.storage.source_registry import SourceRegistry
    from core.storage.studio_store import StudioStore

    for store_cls in (NoteStore, SourceRegistry, ChatHistoryStore, StudioStore, GraphStore):
        store = store_cls(db_path=db_path)
        store_conn = store._conn()
        try:
            assert store_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            store_conn.close()


def test_migration_is_idempotent(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    conn.execute(
        """
        INSERT INTO notebooks (id, name, created_at, updated_at, source_count, owner_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "nb-idempotent",
            "Idempotent Notebook",
            "2026-04-18T00:00:00+00:00",
            "2026-04-18T00:00:00+00:00",
            0,
            None,
        ),
    )
    conn.commit()
    conn.close()

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        row = conn.execute(
            "SELECT id, name FROM notebooks WHERE id = ?",
            ("nb-idempotent",),
        ).fetchone()
        assert row is not None
        assert row["name"] == "Idempotent Notebook"
    finally:
        conn.close()


def test_fk_cascade_notebook_delete_removes_notes(tmp_path):
    from core.storage.notebook_store import NotebookStore
    from core.storage.note_store import NoteStore
    from core.storage.sqlite_db import get_connection

    db_path = tmp_path / "fk.db"
    notebook_store = NotebookStore(db_path=db_path)
    notebook = notebook_store.create("Cascade Notes")
    note_store = NoteStore(db_path=db_path)

    for index in range(3):
        note_store.create(notebook.id, f"note {index}", citations=[])

    assert len(note_store.list_by_notebook(notebook.id)) == 3
    assert notebook_store.delete(notebook.id) is True

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM notes WHERE notebook_id = ?",
            (notebook.id,),
        ).fetchone()
        assert row[0] == 0
    finally:
        conn.close()


def test_fk_cascade_notebook_delete_removes_sources_and_chat_messages(tmp_path):
    from core.storage.chat_history_store import ChatHistoryStore
    from core.storage.notebook_store import NotebookStore
    from core.storage.source_registry import SourceRegistry
    from core.storage.sqlite_db import get_connection

    db_path = tmp_path / "fk.db"
    notebook_store = NotebookStore(db_path=db_path)
    notebook = notebook_store.create("Cascade Sources Chat")
    source_registry = SourceRegistry(db_path=db_path)
    chat_store = ChatHistoryStore(db_path=db_path)

    for index in range(2):
        source_registry.register(
            notebook.id,
            filename=f"doc-{index}.pdf",
            file_path=f"/tmp/doc-{index}.pdf",
        )
        chat_store.append(notebook.id, "user", f"message {index}")

    assert len(source_registry.list_by_notebook(notebook.id)) == 2
    assert len(chat_store.list_by_notebook(notebook.id)) == 2
    assert notebook_store.delete(notebook.id) is True

    conn = get_connection(db_path)
    try:
        source_count = conn.execute(
            "SELECT COUNT(*) FROM sources WHERE notebook_id = ?",
            (notebook.id,),
        ).fetchone()[0]
        message_count = conn.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE notebook_id = ?",
            (notebook.id,),
        ).fetchone()[0]
        assert source_count == 0
        assert message_count == 0
    finally:
        conn.close()


def test_fk_cascade_notebook_delete_removes_studio_outputs(tmp_path):
    from core.storage.notebook_store import NotebookStore
    from core.storage.sqlite_db import get_connection
    from core.storage.studio_store import StudioStore

    db_path = tmp_path / "fk.db"
    notebook_store = NotebookStore(db_path=db_path)
    notebook = notebook_store.create("Cascade Studio")
    studio_store = StudioStore(db_path=db_path)
    studio_store.create(notebook.id, "summary", "content", citations=[])

    assert len(studio_store.list_by_notebook(notebook.id)) == 1
    assert notebook_store.delete(notebook.id) is True

    conn = get_connection(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM studio_outputs WHERE notebook_id = ?",
            (notebook.id,),
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_fk_cascade_notebook_delete_removes_knowledge_graphs(tmp_path):
    from core.storage.graph_store import GraphStore
    from core.storage.notebook_store import NotebookStore
    from core.storage.sqlite_db import get_connection

    db_path = tmp_path / "fk.db"
    notebook_store = NotebookStore(db_path=db_path)
    notebook = notebook_store.create("Cascade Graph")
    graph_store = GraphStore(db_path=db_path)
    graph_store.save(notebook.id, _minimal_graph())

    assert graph_store.exists(notebook.id) is True
    assert notebook_store.delete(notebook.id) is True

    conn = get_connection(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM knowledge_graphs WHERE notebook_id = ?",
            (notebook.id,),
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_fk_reject_note_create_with_missing_notebook(tmp_path):
    from core.storage.exceptions import NotebookNotFound
    from core.storage.note_store import NoteStore

    store = NoteStore(db_path=tmp_path / "fk.db")
    with pytest.raises(NotebookNotFound) as exc_info:
        store.create("ghost", "orphan", citations=[])

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Notebook not found: ghost"


def test_fk_reject_knowledge_graph_create_with_missing_notebook(tmp_path):
    from core.storage.exceptions import NotebookNotFound
    from core.storage.graph_store import GraphStore

    store = GraphStore(db_path=tmp_path / "fk.db")
    with pytest.raises(NotebookNotFound) as exc_info:
        store.save("ghost", _minimal_graph())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Notebook not found: ghost"


def test_foreign_key_check_clean_after_migration(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_orphan_repair_check_reports_counts(tmp_path, _import_sqlite_db, capsys):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    _insert_orphan_note(conn)
    _insert_orphan_graph(conn)
    conn.commit()
    conn.close()

    from scripts import audit_integrity

    exit_code = audit_integrity.main(["--db", str(db_path), "--check"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "notes: 1" in captured.out
    assert "knowledge_graphs: 1" in captured.out
    assert "total: 2" in captured.out


def test_orphan_repair_confirm_deletes_and_emits_audit(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    _insert_orphan_note(conn)
    _insert_orphan_graph(conn)
    conn.commit()
    conn.close()

    from scripts import audit_integrity

    exit_code = audit_integrity.main(["--db", str(db_path), "--repair", "--confirm"])
    assert exit_code == 0

    conn = sqlite_db.get_connection(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM knowledge_graphs").fetchone()[0] == 0
        rows = conn.execute(
            """
            SELECT event, payload_json
            FROM audit_events
            WHERE event = ?
            ORDER BY ts_utc ASC
            """,
            ("integrity.repair",),
        ).fetchall()
        assert len(rows) == 2
        payloads = [json.loads(row["payload_json"]) for row in rows]
        assert {payload["orphan_table"] for payload in payloads} == {
            "notes",
            "knowledge_graphs",
        }
        assert all(payload["parent_table"] == "notebooks" for payload in payloads)
        assert all(payload["parent_column"] == "id" for payload in payloads)
    finally:
        conn.close()


def test_orphan_repair_is_idempotent(tmp_path, _import_sqlite_db):
    sqlite_db = _import_sqlite_db
    db_path = tmp_path / "fk.db"

    conn = sqlite_db.get_connection(db_path)
    sqlite_db.init_schema(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    _insert_orphan_note(conn)
    conn.commit()
    conn.close()

    from scripts import audit_integrity

    first = audit_integrity.repair_orphans(db_path, confirm=True)
    second = audit_integrity.repair_orphans(db_path, confirm=True)

    assert first["notes"] == 1
    assert second["notes"] == 0
    assert sum(second.values()) == 0


def test_audit_event_integrity_repair_in_enum():
    from core.governance.audit_events import AuditEvent
    from core.governance.audit_redact import redact

    assert AuditEvent.INTEGRITY_REPAIR.value == "integrity.repair"
    payload = redact(
        {
            "orphan_table": "notes",
            "orphan_id": "orphan-note",
            "parent_table": "notebooks",
            "parent_column": "id",
            "secret": "must-drop",
        }
    )
    assert payload == {
        "orphan_table": "notes",
        "orphan_id": "orphan-note",
        "parent_table": "notebooks",
        "parent_column": "id",
    }


def test_migration_refuses_to_start_with_orphans_without_repair(tmp_path):
    """Direct FK rebuild without the repair hook must reject existing orphans."""
    from core.storage.migrations import v4_2_t5_fk_enforcement as migration
    from core.storage.sqlite_db import get_connection, init_schema

    db_path = tmp_path / "fk.db"
    conn = get_connection(db_path)
    init_schema(conn)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            """
            INSERT INTO notes (id, notebook_id, title, content, citations, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "orphan-note",
                "ghost",
                "Orphan",
                "content",
                "[]",
                "2026-04-18T00:00:00+00:00",
                "2026-04-18T00:00:00+00:00",
            ),
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")

        with pytest.raises(sqlite3.IntegrityError):
            migration.apply(conn, repair=False)
    finally:
        conn.close()
