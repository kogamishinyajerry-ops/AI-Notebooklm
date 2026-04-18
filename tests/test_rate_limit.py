from __future__ import annotations

import concurrent.futures
import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.middleware import SlowAPIMiddleware

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


def _build_chat_client(
    rate_limit_module,
    *,
    inject_principal: bool = False,
) -> TestClient:
    app = FastAPI()
    rate_limit_module.setup_rate_limit(app)
    app.add_middleware(SlowAPIMiddleware)

    if inject_principal:
        @app.middleware("http")
        async def add_principal(request: Request, call_next):
            principal_id = request.headers.get("x-principal-id")
            if principal_id:
                request.state.principal = SimpleNamespace(principal_id=principal_id)
            return await call_next(request)

    @app.post("/api/v1/chat")
    @rate_limit_module.limiter.limit(
        rate_limit_module._get_chat_rate,
        error_message=rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL,
    )
    async def chat(request: Request):
        return {"ok": True}

    return TestClient(app)


def _load_rate_limit_module():
    import core.governance.rate_limit as rate_limit_module

    return importlib.reload(rate_limit_module)


def test_chat_rate_limit_enforced(fresh_rate_limit_state):
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(30):
        response = client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "alice"},
        )
        assert response.status_code == 200

    response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert response.status_code == 429
    assert response.json()["detail"] == rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL


def test_chat_rate_limit_per_principal_isolation(fresh_rate_limit_state):
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(30):
        response = client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "alice"},
        )
        assert response.status_code == 200

    alice_limited = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    bob_allowed = client.post("/api/v1/chat", headers={"x-principal-id": "bob"})

    assert alice_limited.status_code == 429
    assert bob_allowed.status_code == 200


def test_429_response_format(fresh_rate_limit_state, monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "1/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    allowed = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    blocked = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert allowed.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json() == {
        "detail": rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL,
        "retry_after": 60,
    }
    assert blocked.headers["Retry-After"] == "60"


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


def test_env_override_chat_rate(fresh_rate_limit_state, monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "5/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(5):
        response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
        assert response.status_code == 200

    blocked = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert blocked.status_code == 429
    assert blocked.json()["detail"] == rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL


def test_env_override_invalid_format_fallback(fresh_rate_limit_state, monkeypatch, caplog):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "invalid")
    caplog.set_level("WARNING", logger="comac.rate_limit")

    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    assert rate_limit_module._get_chat_rate() == "30/minute"
    assert any(
        "NOTEBOOKLM_CHAT_RATE='invalid' is invalid" in record.getMessage()
        for record in caplog.records
    )

    response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    assert response.status_code == 200


def test_auth_disabled_falls_back_to_ip(fresh_rate_limit_state, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "5/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=False)

    for _ in range(5):
        response = client.post("/api/v1/chat")
        assert response.status_code == 200

    blocked = client.post("/api/v1/chat")

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == f"Rate limit exceeded: {rate_limit_module.CHAT_RATE_DIMENSION}"
    )
