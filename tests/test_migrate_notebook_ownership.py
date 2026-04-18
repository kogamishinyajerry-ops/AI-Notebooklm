"""V4.2-T4: tests for scripts/migrate_notebook_ownership.py.

Contract: freeze pack docs/v4_2_t4_freeze_pack.md (FD-1..FD-10).
Each test scopes its own SQLite + env so there is no cross-test leakage.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from core.governance.audit_events import AuditEvent
from core.governance.audit_logger import AuditLogger
from core.storage.sqlite_db import get_connection, init_schema
from scripts import migrate_notebook_ownership as mig


def _mk_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "notebooks.db"
    conn = get_connection(db_path)
    try:
        init_schema(conn)
    finally:
        conn.close()
    return db_path


def _seed_notebook(db_path: Path, notebook_id: str, owner_id, created_at: str = "2026-03-01T00:00:00Z") -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO notebooks (id, name, created_at, updated_at, owner_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (notebook_id, f"NB {notebook_id}", created_at, created_at, owner_id),
        )
        conn.commit()
    finally:
        conn.close()


def _count_with_owner(db_path: Path, owner_id: str) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM notebooks WHERE owner_id = ?", (owner_id,)
        ).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path):
    return _mk_db(tmp_path)


@pytest.fixture
def audit_logger(tmp_path):
    return AuditLogger(db_path=tmp_path / "audit.db")


@pytest.fixture
def alice_env(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")


# ---------------------------------------------------------------------------
# --report-only
# ---------------------------------------------------------------------------


def test_report_only_lists_legacy_rows(db, capsys):
    _seed_notebook(db, "nb-1", None, created_at="2025-01-10T00:00:00Z")
    _seed_notebook(db, "nb-2", "", created_at="2025-05-20T00:00:00Z")
    _seed_notebook(db, "nb-3", "alice", created_at="2026-04-01T00:00:00Z")

    out = io.StringIO()
    rc = mig.main(["--db", str(db), "--report-only"], out=out)
    assert rc == mig.EXIT_OK
    text = out.getvalue()
    assert "legacy notebook rows: 2" in text
    assert "2025: 2" in text
    assert "nb-1" in text and "nb-2" in text
    assert "nb-3" not in text


def test_report_only_exits_zero_when_empty(db, capsys):
    _seed_notebook(db, "nb-1", "alice")
    out = io.StringIO()
    rc = mig.main(["--db", str(db), "--report-only"], out=out)
    assert rc == mig.EXIT_OK
    assert "nothing to report" in out.getvalue()


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


def test_dry_run_prints_plan_and_exits_1(db, alice_env):
    _seed_notebook(db, "nb-legacy-1", None)
    _seed_notebook(db, "nb-legacy-2", "")
    _seed_notebook(db, "nb-alice", "alice")

    out = io.StringIO()
    rc = mig.main(["--db", str(db), "--owner", "alice", "--dry-run"], out=out)
    assert rc == mig.EXIT_DRY_RUN_PENDING
    text = out.getvalue()
    assert "ASSIGN" in text
    assert "nb-legacy-1" in text and "nb-legacy-2" in text
    assert "nb-alice" not in text


def test_dry_run_no_db_writes(db, alice_env):
    _seed_notebook(db, "nb-legacy", None)
    mig.main(["--db", str(db), "--owner", "alice", "--dry-run"], out=io.StringIO())
    assert _count_with_owner(db, "alice") == 0


def test_dry_run_no_audit_emission(db, alice_env, audit_logger):
    _seed_notebook(db, "nb-legacy", None)
    mig.main(
        ["--db", str(db), "--owner", "alice", "--dry-run"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    events = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    assert events == []


def test_dry_run_exits_0_when_nothing_pending(db, alice_env):
    _seed_notebook(db, "nb-alice", "alice")
    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--dry-run"], out=io.StringIO()
    )
    assert rc == mig.EXIT_OK


# ---------------------------------------------------------------------------
# real migration
# ---------------------------------------------------------------------------


def test_migrate_assigns_owner_to_legacy_rows(db, alice_env, audit_logger):
    _seed_notebook(db, "nb-1", None)
    _seed_notebook(db, "nb-2", "")

    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    assert rc == mig.EXIT_OK
    assert _count_with_owner(db, "alice") == 2


def test_migrate_idempotent_second_run_is_noop(db, alice_env, audit_logger):
    _seed_notebook(db, "nb-1", None)

    mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    events_after_first = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    assert len(events_after_first) == 1

    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    assert rc == mig.EXIT_OK
    events_after_second = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    # No new audit rows because no rows were migrated.
    assert len(events_after_second) == 1


def test_migrate_skips_non_legacy_without_force(db, alice_env):
    _seed_notebook(db, "nb-bob", "bob")

    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"], out=io.StringIO()
    )
    assert rc == mig.EXIT_OK
    # bob's row untouched.
    assert _count_with_owner(db, "bob") == 1
    assert _count_with_owner(db, "alice") == 0


def test_migrate_force_overwrites_non_legacy(db, alice_env, audit_logger):
    _seed_notebook(db, "nb-bob", "bob")

    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--force", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    assert rc == mig.EXIT_OK
    assert _count_with_owner(db, "alice") == 1
    assert _count_with_owner(db, "bob") == 0

    events = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    assert len(events) == 1
    assert '"migrate.forced":true' in events[0].payload_json


def test_migrate_empty_string_owner_treated_as_legacy(db, alice_env):
    _seed_notebook(db, "nb-empty", "")
    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"], out=io.StringIO()
    )
    assert rc == mig.EXIT_OK
    assert _count_with_owner(db, "alice") == 1


def test_migrate_filters_by_notebook_id(db, alice_env):
    _seed_notebook(db, "nb-1", None)
    _seed_notebook(db, "nb-2", None)

    rc = mig.main(
        [
            "--db", str(db), "--owner", "alice",
            "--notebook-id", "nb-1", "--assume-yes",
        ],
        out=io.StringIO(),
    )
    assert rc == mig.EXIT_OK
    assert _count_with_owner(db, "alice") == 1
    # nb-2 still NULL.
    conn = get_connection(db)
    try:
        row = conn.execute("SELECT owner_id FROM notebooks WHERE id=?", ("nb-2",)).fetchone()
        assert row[0] is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_migrate_unknown_principal_exits_2(db, alice_env):
    _seed_notebook(db, "nb-1", None)
    rc = mig.main(
        ["--db", str(db), "--owner", "carol", "--assume-yes"], out=io.StringIO()
    )
    assert rc == mig.EXIT_VALIDATION_FAILED
    assert _count_with_owner(db, "carol") == 0


def test_migrate_missing_api_keys_exits_2(db, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    _seed_notebook(db, "nb-1", None)
    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"], out=io.StringIO()
    )
    assert rc == mig.EXIT_VALIDATION_FAILED


def test_migrate_missing_owner_flag_exits_2(db, alice_env):
    _seed_notebook(db, "nb-1", None)
    rc = mig.main(["--db", str(db), "--assume-yes"], out=io.StringIO())
    assert rc == mig.EXIT_VALIDATION_FAILED


# ---------------------------------------------------------------------------
# audit emission + transactional safety
# ---------------------------------------------------------------------------


def test_migrate_emits_audit_row_per_notebook(db, alice_env, audit_logger):
    _seed_notebook(db, "nb-1", None)
    _seed_notebook(db, "nb-2", "")

    mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    events = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    assert len(events) == 2
    for e in events:
        assert e.actor_type == "system"
        assert e.principal_id == "system:migrate_notebook_ownership"
        assert e.resource_type == "notebook"
        assert '"migrate.to_owner":"alice"' in e.payload_json
        assert '"migrate.forced":false' in e.payload_json


def test_migrate_rolls_back_on_row_failure(db, alice_env, audit_logger, monkeypatch):
    _seed_notebook(db, "nb-1", None)
    _seed_notebook(db, "nb-2", None)

    # Force _apply_migration's inner UPDATE to claim 0 rows affected, which
    # must trigger rollback and leave the DB untouched.
    real_connect = mig.get_connection

    class _FailingConn:
        def __init__(self, real): self._r = real
        def __getattr__(self, n): return getattr(self._r, n)
        def execute(self, sql, params=()):
            if sql.startswith("UPDATE notebooks SET owner_id"):
                class _Res:
                    rowcount = 0
                return _Res()
            return self._r.execute(sql, params)

    def fake_connect(path):
        return _FailingConn(real_connect(path))

    monkeypatch.setattr(mig, "get_connection", fake_connect)

    rc = mig.main(
        ["--db", str(db), "--owner", "alice", "--assume-yes"],
        out=io.StringIO(),
        audit_logger=audit_logger,
    )
    assert rc == mig.EXIT_IO_ERROR
    # DB rolled back — nobody migrated.
    assert _count_with_owner(db, "alice") == 0
    # No audit rows emitted (audit runs after commit).
    events = audit_logger.store.query_events(
        event=AuditEvent.NOTEBOOK_MIGRATE_OWNER.value
    ).items
    assert events == []
