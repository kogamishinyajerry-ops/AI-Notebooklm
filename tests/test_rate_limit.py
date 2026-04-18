from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from core.governance.quota_store import DailyUploadQuota, NotebookCountCap, QuotaExceededError
from core.storage.sqlite_db import get_connection, init_schema


class _TimeTravel:
    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def set(self, year: int, month: int, day: int) -> None:
        self._now = datetime(year, month, day, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now


def _insert_notebook(db_path: Path, owner_id: str, index: int) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO notebooks (id, name, created_at, updated_at, source_count, owner_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{owner_id}-{index}-{uuid4()}",
                f"{owner_id}-notebook-{index}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                0,
                owner_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def api_keys_env(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    yield
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)


@pytest.fixture
def time_travel() -> _TimeTravel:
    return _TimeTravel()


@pytest.fixture
def fresh_rate_limit_state(tmp_path, monkeypatch) -> Path:
    for env_name in (
        "NOTEBOOKLM_CHAT_RATE",
        "NOTEBOOKLM_UPLOAD_DAILY_BYTES",
        "NOTEBOOKLM_NOTEBOOK_MAX",
    ):
        monkeypatch.delenv(env_name, raising=False)

    db_path = tmp_path / "notebooks.db"
    conn = get_connection(db_path)
    init_schema(conn)
    conn.execute("DELETE FROM daily_upload_usage")
    conn.commit()
    conn.close()
    return db_path


def test_upload_daily_quota_enforced(fresh_rate_limit_state):
    store = DailyUploadQuota(db_path=fresh_rate_limit_state)

    assert store.check_and_record("alice", 499 * 1024 * 1024) == 499 * 1024 * 1024

    with pytest.raises(QuotaExceededError) as exc_info:
        store.check_and_record("alice", 2 * 1024 * 1024)

    assert exc_info.value.detail == "Rate limit exceeded: upload_bytes"
    assert exc_info.value.retry_after == 60


def test_upload_quota_persists_across_restart(fresh_rate_limit_state):
    store = DailyUploadQuota(db_path=fresh_rate_limit_state)
    assert store.check_and_record("alice", 400 * 1024 * 1024) == 400 * 1024 * 1024

    restarted_store = DailyUploadQuota(db_path=fresh_rate_limit_state)

    with pytest.raises(QuotaExceededError):
        restarted_store.check_and_record("alice", 200 * 1024 * 1024)


def test_upload_quota_resets_next_day(fresh_rate_limit_state, time_travel):
    time_travel.set(2026, 1, 1)
    store = DailyUploadQuota(db_path=fresh_rate_limit_state, now_fn=time_travel.now)
    assert store.check_and_record("alice", 500 * 1024 * 1024) == 500 * 1024 * 1024

    with pytest.raises(QuotaExceededError):
        store.check_and_record("alice", 1)

    time_travel.set(2026, 1, 2)
    assert store.check_and_record("alice", 200 * 1024 * 1024) == 200 * 1024 * 1024


def test_notebook_count_hard_cap(fresh_rate_limit_state):
    cap = NotebookCountCap(db_path=fresh_rate_limit_state)
    for index in range(50):
        _insert_notebook(fresh_rate_limit_state, "alice", index)

    with pytest.raises(QuotaExceededError) as exc_info:
        cap.check("alice")

    assert exc_info.value.detail == "Rate limit exceeded: notebook_count"
    assert exc_info.value.retry_after == 60


def test_notebook_cap_per_owner(fresh_rate_limit_state):
    cap = NotebookCountCap(db_path=fresh_rate_limit_state)
    for index in range(50):
        _insert_notebook(fresh_rate_limit_state, "alice", index)
    _insert_notebook(fresh_rate_limit_state, "bob", 0)

    with pytest.raises(QuotaExceededError):
        cap.check("alice")

    assert cap.check("bob") == 1


def test_daily_upload_usage_table_atomic(fresh_rate_limit_state):
    chunk_size = 100 * 1024 * 1024
    store = DailyUploadQuota(
        db_path=fresh_rate_limit_state,
        daily_limit=3 * 1024 * 1024 * 1024,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(store.check_and_record, "alice", chunk_size)
            for _ in range(20)
        ]
        results = [future.result() for future in futures]

    assert len(results) == 20
    assert store.get_usage("alice") == 20 * chunk_size
