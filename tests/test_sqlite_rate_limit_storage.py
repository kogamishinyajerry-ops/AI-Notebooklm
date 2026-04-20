from __future__ import annotations

from core.governance import sqlite_rate_limit_storage as storage_module
from core.governance.sqlite_rate_limit_storage import SQLiteFixedWindowStorage


def test_sqlite_rate_limit_storage_shares_state_across_instances(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_SQLITE_POOL_SIZE", raising=False)
    db_path = tmp_path / "notebooks.db"

    first = SQLiteFixedWindowStorage(db_path)
    second = SQLiteFixedWindowStorage(db_path)

    assert first.incr("chat:alice", expiry=60) == 1
    assert second.get("chat:alice") == 1
    assert second.incr("chat:alice", expiry=60) == 2
    assert first.get("chat:alice") == 2


def test_sqlite_rate_limit_storage_expires_and_resets_counter(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_SQLITE_POOL_SIZE", raising=False)
    now = [1_700_000_000.0]
    monkeypatch.setattr(storage_module.time, "time", lambda: now[0])
    db_path = tmp_path / "notebooks.db"
    store = SQLiteFixedWindowStorage(db_path)

    assert store.incr("chat:alice", expiry=60) == 1
    assert store.incr("chat:alice", expiry=60) == 2
    assert store.get("chat:alice") == 2

    now[0] += 61

    assert store.get("chat:alice") == 0
    assert store.incr("chat:alice", expiry=60) == 1
