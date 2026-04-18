"""V4.2-T3 Step 4: QuotaStore admin bypass + cross-principal snapshot.

Admin bypass contract (FD-10): admin principal skips the cap check but the
underlying usage is *still recorded* so the admin dashboard can observe real
traffic (including admin's own uploads) with no hidden accounting.

Snapshot contract: aggregate per-principal usage for the admin dashboard,
one query per class (no N+1).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.governance.quota_store import (
    DailyUploadQuota,
    NotebookCountCap,
    QuotaExceededError,
)
from core.storage.sqlite_db import get_connection, init_schema


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "notebooks.db"
    conn = get_connection(path)
    try:
        init_schema(conn)
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------
# Upload quota bypass
# ---------------------------------------------------------------------------


def test_daily_upload_bypass_over_limit(db_path):
    """is_admin=True skips the daily cap; still returns total bytes used."""
    store = DailyUploadQuota(db_path=db_path, daily_limit=1024)
    # Over the cap in one shot — would normally raise.
    used = store.check_and_record("root", 2048, is_admin=True)
    assert used == 2048


def test_daily_upload_bypass_still_records(db_path):
    """Admin bypass is *not* silent: usage must still appear in get_usage."""
    store = DailyUploadQuota(db_path=db_path, daily_limit=1024)
    store.check_and_record("root", 2048, is_admin=True)
    assert store.get_usage("root") == 2048


def test_daily_upload_non_admin_still_enforced(db_path):
    """Backward compat: is_admin default False keeps enforcement."""
    store = DailyUploadQuota(db_path=db_path, daily_limit=1024)
    store.check_and_record("alice", 500)
    with pytest.raises(QuotaExceededError):
        store.check_and_record("alice", 1000)
    # Signature backward compat: omitting is_admin must still work.
    assert store.get_usage("alice") == 500


def test_daily_upload_admin_after_non_admin_hit_cap(db_path):
    """Admin bypass works even after non-admin already hit the cap."""
    store = DailyUploadQuota(db_path=db_path, daily_limit=1024)
    store.check_and_record("alice", 1024)  # fill it
    with pytest.raises(QuotaExceededError):
        store.check_and_record("alice", 1)
    # Different admin principal over their own cap — allowed.
    used = store.check_and_record("root", 5000, is_admin=True)
    assert used == 5000


# ---------------------------------------------------------------------------
# Notebook count cap bypass
# ---------------------------------------------------------------------------


def _seed_notebooks(db_path: Path, owner_id: str, n: int) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for i in range(n):
            conn.execute(
                "INSERT INTO notebooks (id, name, created_at, updated_at, owner_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"nb-{owner_id}-{i}",
                    f"Notebook {i}",
                    "2026-04-18T10:00:00Z",
                    "2026-04-18T10:00:00Z",
                    owner_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_notebook_cap_check_admin_bypass(db_path):
    cap = NotebookCountCap(db_path=db_path, max_count=3)
    _seed_notebooks(db_path, "root", 5)  # already over cap
    # Non-admin would raise; admin returns count without raising.
    assert cap.check("root", is_admin=True) == 5


def test_notebook_cap_check_non_admin_still_raises(db_path):
    cap = NotebookCountCap(db_path=db_path, max_count=3)
    _seed_notebooks(db_path, "alice", 3)
    with pytest.raises(QuotaExceededError):
        cap.check("alice")
    # Default (no is_admin) keeps legacy behavior.
    with pytest.raises(QuotaExceededError):
        cap.check("alice", is_admin=False)


def test_notebook_cap_execute_with_slot_admin_bypass(db_path):
    """execute_with_slot honors is_admin — action still runs inside the tx."""
    cap = NotebookCountCap(db_path=db_path, max_count=2)
    _seed_notebooks(db_path, "root", 2)  # at cap

    def insert(conn):
        conn.execute(
            "INSERT INTO notebooks (id, name, created_at, updated_at, owner_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("nb-extra", "extra", "2026-04-18T10:00:00Z", "2026-04-18T10:00:00Z", "root"),
        )
        return "ok"

    # Non-admin would raise; admin path commits the insert.
    result = cap.execute_with_slot("root", insert, is_admin=True)
    assert result == "ok"
    assert cap.count("root") == 3


def test_notebook_cap_execute_with_slot_non_admin_still_raises(db_path):
    cap = NotebookCountCap(db_path=db_path, max_count=1)
    _seed_notebooks(db_path, "alice", 1)

    def insert(conn):
        conn.execute(
            "INSERT INTO notebooks (id, name, created_at, updated_at, owner_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("nb-x", "x", "2026-04-18T10:00:00Z", "2026-04-18T10:00:00Z", "alice"),
        )

    with pytest.raises(QuotaExceededError):
        cap.execute_with_slot("alice", insert)


# ---------------------------------------------------------------------------
# Cross-principal snapshots
# ---------------------------------------------------------------------------


def test_daily_upload_snapshot_all_principals(db_path):
    """snapshot_all_principals aggregates per-principal usage for a given date."""
    store = DailyUploadQuota(db_path=db_path, daily_limit=10 * 1024 * 1024)
    store.check_and_record("alice", 1024)
    store.check_and_record("bob", 2048)
    store.check_and_record("alice", 512)  # alice accumulates

    snapshot = store.snapshot_all_principals()
    assert isinstance(snapshot, list)
    # Default order: bytes_used DESC for dashboard relevance
    by_pid = {row["principal_id"]: row for row in snapshot}
    assert by_pid["alice"]["bytes_used"] == 1536
    assert by_pid["bob"]["bytes_used"] == 2048
    assert by_pid["alice"]["daily_limit"] == 10 * 1024 * 1024


def test_daily_upload_snapshot_empty(db_path):
    store = DailyUploadQuota(db_path=db_path)
    assert store.snapshot_all_principals() == []


def test_daily_upload_snapshot_respects_usage_date(db_path):
    """Snapshot filters by given date; cross-day usage is not aggregated."""

    class FrozenClock:
        def __init__(self, ts: str) -> None:
            self.ts = ts

        def __call__(self) -> datetime:
            return datetime.fromisoformat(self.ts).replace(tzinfo=timezone.utc)

    clock = FrozenClock("2026-04-18T10:00:00")
    store = DailyUploadQuota(db_path=db_path, now_fn=clock)
    store.check_and_record("alice", 100)
    clock.ts = "2026-04-19T10:00:00"
    store.check_and_record("alice", 200)
    # Default uses "today" per now_fn -> 2026-04-19
    snap_today = store.snapshot_all_principals()
    assert snap_today == [
        {
            "principal_id": "alice",
            "usage_date": "2026-04-19",
            "bytes_used": 200,
            "daily_limit": store.daily_limit,
        }
    ]
    # Explicit date param lets admin page any historical day.
    snap_yesterday = store.snapshot_all_principals(usage_date="2026-04-18")
    assert snap_yesterday == [
        {
            "principal_id": "alice",
            "usage_date": "2026-04-18",
            "bytes_used": 100,
            "daily_limit": store.daily_limit,
        }
    ]


def test_notebook_cap_snapshot_all_owners(db_path):
    cap = NotebookCountCap(db_path=db_path, max_count=50)
    _seed_notebooks(db_path, "alice", 3)
    _seed_notebooks(db_path, "bob", 7)
    _seed_notebooks(db_path, "carol", 1)

    snapshot = cap.snapshot_all_principals()
    by_pid = {row["principal_id"]: row for row in snapshot}
    assert by_pid["alice"]["count"] == 3
    assert by_pid["bob"]["count"] == 7
    assert by_pid["carol"]["count"] == 1
    assert all(row["max_count"] == 50 for row in snapshot)


def test_notebook_cap_snapshot_empty(db_path):
    cap = NotebookCountCap(db_path=db_path)
    assert cap.snapshot_all_principals() == []
