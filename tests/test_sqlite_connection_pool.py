from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_pool(monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_SQLITE_POOL_SIZE", raising=False)
    from core.storage.sqlite_db import close_connection_pools

    close_connection_pools()
    yield
    close_connection_pools()


def test_pool_disabled_by_default_closes_connection(tmp_path):
    from core.storage.sqlite_db import get_connection

    db_path = tmp_path / "notebooks.db"
    conn = get_connection(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.close()

    with pytest.raises(Exception):
        conn.execute("SELECT 1")


def test_pool_reuses_connection_when_enabled(tmp_path, monkeypatch):
    from core.storage.sqlite_db import get_connection

    monkeypatch.setenv("NOTEBOOKLM_SQLITE_POOL_SIZE", "1")
    db_path = tmp_path / "notebooks.db"

    conn1 = get_connection(db_path)
    conn1.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn1.close()

    conn2 = get_connection(db_path)
    try:
        assert conn2 is conn1
        assert conn2.execute("SELECT COUNT(*) AS count FROM t").fetchone()["count"] == 0
    finally:
        conn2.close()


def test_pool_rolls_back_uncommitted_work_on_return(tmp_path, monkeypatch):
    from core.storage.sqlite_db import get_connection

    monkeypatch.setenv("NOTEBOOKLM_SQLITE_POOL_SIZE", "1")
    db_path = tmp_path / "notebooks.db"

    conn = get_connection(db_path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()

    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO t (value) VALUES ('uncommitted')")
    conn.close()

    reused = get_connection(db_path)
    try:
        row = reused.execute("SELECT COUNT(*) AS count FROM t").fetchone()
        assert row["count"] == 0
    finally:
        reused.close()


def test_pool_reapplies_pragmas_on_reuse(tmp_path, monkeypatch):
    from core.storage.sqlite_db import get_connection

    monkeypatch.setenv("NOTEBOOKLM_SQLITE_POOL_SIZE", "1")
    db_path = tmp_path / "notebooks.db"

    conn = get_connection(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.close()

    reused = get_connection(db_path)
    try:
        assert reused.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert reused.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        reused.close()


def test_invalid_pool_size_disables_pool(tmp_path, monkeypatch):
    from core.storage.sqlite_db import get_connection

    monkeypatch.setenv("NOTEBOOKLM_SQLITE_POOL_SIZE", "not-an-int")
    db_path = tmp_path / "notebooks.db"

    conn = get_connection(db_path)
    conn.close()

    with pytest.raises(Exception):
        conn.execute("SELECT 1")
