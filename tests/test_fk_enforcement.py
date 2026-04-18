from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


@pytest.fixture(autouse=True)
def _stub_transaction_module(tmp_path):
    sys.modules.pop("core.ingestion.transaction", None)
    transaction_mod = types.ModuleType("core.ingestion.transaction")
    transaction_mod.DEFAULT_SPACES_DIR = tmp_path / "spaces"
    transaction_mod.iter_space_ids = MagicMock(return_value=[])
    transaction_mod.utc_now_iso = lambda: "2026-04-18T00:00:00+00:00"
    sys.modules["core.ingestion.transaction"] = transaction_mod
    yield
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
    from core.storage.note_store import NoteStore
    from core.storage.source_registry import SourceRegistry

    for store_cls in (NoteStore, SourceRegistry, ChatHistoryStore):
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
