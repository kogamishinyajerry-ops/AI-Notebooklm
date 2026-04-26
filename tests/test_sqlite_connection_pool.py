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


# ---------------------------------------------------------------------------
# W-V43-11.9 (closes Codex finding RL-53-03): shutdown hook wiring.
# ---------------------------------------------------------------------------


def test_shutdown_hook_calls_close_connection_pools():
    """The FastAPI ``shutdown`` event handler in apps/api/main.py must call
    close_connection_pools so idle pooled SQLite connections are released
    cleanly when the worker exits. Verified by patching the function and
    asserting the hook invokes it exactly once."""
    from unittest.mock import patch

    from apps.api import main as api_main

    handlers = api_main.app.router.on_shutdown
    assert handlers, "FastAPI app has no shutdown handlers wired"

    with patch("core.storage.sqlite_db.close_connection_pools") as mock_close:
        for handler in handlers:
            handler()
        assert mock_close.call_count >= 1, (
            "Shutdown hook must call close_connection_pools at least once "
            "(W-V43-11.9 / RL-53-03 invariant)."
        )


def test_shutdown_hook_swallows_exceptions(caplog):
    """Observability rule: a failure in close_connection_pools must not
    propagate out of the shutdown hook (would prevent the worker from
    exiting cleanly). The handler logs and continues."""
    import logging
    from unittest.mock import patch

    from apps.api import main as api_main

    with caplog.at_level(logging.ERROR), patch(
        "core.storage.sqlite_db.close_connection_pools",
        side_effect=RuntimeError("boom"),
    ):
        for handler in api_main.app.router.on_shutdown:
            handler()
    assert any(
        "close_connection_pools failed during shutdown" in rec.getMessage()
        for rec in caplog.records
    ), "shutdown failure must be logged at ERROR"


def test_shutdown_hook_idempotent_no_pools(tmp_path, monkeypatch):
    """When no pools were created (default config: pool size unset), the
    shutdown hook must still run cleanly — no exception, no error log."""
    import logging

    from apps.api import main as api_main
    from core.storage.sqlite_db import close_connection_pools

    # Ensure no residual pools.
    close_connection_pools()

    caplog_records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = caplog_records.append  # type: ignore[assignment]
    api_main.logger.addHandler(handler)
    try:
        for fn in api_main.app.router.on_shutdown:
            fn()
    finally:
        api_main.logger.removeHandler(handler)
    error_records = [r for r in caplog_records if r.levelno >= logging.ERROR]
    assert error_records == [], (
        "shutdown with no pools must be silent at ERROR; got: "
        f"{[r.getMessage() for r in error_records]}"
    )
