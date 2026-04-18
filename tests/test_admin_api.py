"""V4.2-T3 Step 6: admin API route tests.

Isolated FastAPI app that mounts only the admin router — keeps test DB state
scoped per-test and avoids pulling in the full main.py startup (with its ML
module stubs and static file mount).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.admin_routes import router as admin_router
from core.governance.admin import ADMIN_PRINCIPALS_ENV
from core.governance.audit_events import AuditEvent
from core.governance.audit_logger import AuditLogger
from core.governance.audit_store import AuditRecord, AuditStore
from core.governance.quota_store import DailyUploadQuota, NotebookCountCap
from core.storage.sqlite_db import get_connection, init_schema


def _mk_record(event_id: str, ts: str, *, principal: str = "alice") -> AuditRecord:
    return AuditRecord(
        event_id=event_id,
        ts_utc=ts,
        event="notebook.create",
        outcome="success",
        actor_type="user",
        principal_id=principal,
        request_id=f"req-{event_id}",
        remote_addr="127.0.0.1",
        resource_type="notebook",
        resource_id=f"nb-{event_id}",
        parent_resource_id="",
        http_status=200,
        error_code="",
        payload_json="{}",
    )


def _seed_notebook(db_path: Path, owner_id: str, n: int) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        for i in range(n):
            conn.execute(
                "INSERT INTO notebooks (id, name, created_at, updated_at, owner_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"nb-{owner_id}-{i}",
                    f"NB{i}",
                    "2026-04-18T10:00:00Z",
                    "2026-04-18T10:00:00Z",
                    owner_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    """App wired with admin router + fresh SQLite DB + alice as admin."""
    db_path = tmp_path / "admin.db"
    conn = get_connection(db_path)
    try:
        init_schema(conn)
    finally:
        conn.close()

    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")

    app = FastAPI()
    audit_logger = AuditLogger(db_path=db_path)
    app.state.audit_store = audit_logger.store
    app.state.audit_logger = audit_logger
    app.state.upload_quota = DailyUploadQuota(db_path=db_path, daily_limit=10 * 1024 * 1024)
    app.state.notebook_cap = NotebookCountCap(db_path=db_path, max_count=50)
    app.include_router(admin_router)

    client = TestClient(app)
    # Expose helpers so individual tests can seed data.
    client.db_path = db_path  # type: ignore[attr-defined]
    client.app_obj = app  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# /api/v1/admin/health
# ---------------------------------------------------------------------------


def test_admin_health_grants_admin(admin_client):
    r = admin_client.get("/api/v1/admin/health", headers={"x-api-key": "key-alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["auth_enabled"] is True
    assert body["admin_count"] == 1
    assert body["caller"] == {"principal_id": "alice", "is_admin": True}
    assert isinstance(body["uptime_sec"], int)


def test_admin_health_forbids_non_admin(admin_client):
    r = admin_client.get("/api/v1/admin/health", headers={"x-api-key": "key-bob"})
    assert r.status_code == 403


def test_admin_health_rejects_anonymous(admin_client):
    r = admin_client.get("/api/v1/admin/health")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /api/v1/admin/audit/events
# ---------------------------------------------------------------------------


def test_admin_audit_events_returns_desc(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    for i in range(5):
        store.append(_mk_record(f"e{i}", f"2026-04-18T10:00:0{i}Z"))

    # Filter by event to exclude the admin.access audit emitted by this call.
    r = admin_client.get(
        "/api/v1/admin/audit/events?event=notebook.create",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [it["event_id"] for it in body["items"]]
    assert ids == ["e4", "e3", "e2", "e1", "e0"]
    assert body["next_cursor"] is None


def test_admin_audit_events_pagination(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    for i in range(8):
        store.append(_mk_record(f"e{i}", f"2026-04-18T10:00:0{i}Z"))

    page1 = admin_client.get(
        "/api/v1/admin/audit/events?limit=3&event=notebook.create",
        headers={"x-api-key": "key-alice"},
    ).json()
    assert [it["event_id"] for it in page1["items"]] == ["e7", "e6", "e5"]
    assert page1["next_cursor"] is not None

    page2 = admin_client.get(
        f"/api/v1/admin/audit/events?limit=3&event=notebook.create&cursor={page1['next_cursor']}",
        headers={"x-api-key": "key-alice"},
    ).json()
    assert [it["event_id"] for it in page2["items"]] == ["e4", "e3", "e2"]


def test_admin_audit_events_filter_by_principal(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    store.append(_mk_record("e1", "2026-04-18T10:00:01Z", principal="alice"))
    store.append(_mk_record("e2", "2026-04-18T10:00:02Z", principal="bob"))
    store.append(_mk_record("e3", "2026-04-18T10:00:03Z", principal="alice"))

    r = admin_client.get(
        "/api/v1/admin/audit/events?principal_id=bob",
        headers={"x-api-key": "key-alice"},
    )
    body = r.json()
    assert [it["event_id"] for it in body["items"]] == ["e2"]


def test_admin_audit_events_invalid_cursor_returns_400(admin_client):
    r = admin_client.get(
        "/api/v1/admin/audit/events?cursor=not-base64!!!",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 400


def test_admin_audit_events_forbids_non_admin(admin_client):
    r = admin_client.get(
        "/api/v1/admin/audit/events",
        headers={"x-api-key": "key-bob"},
    )
    assert r.status_code == 403


def test_admin_audit_events_limit_bounds(admin_client):
    # FastAPI Query(ge=1, le=MAX_QUERY_LIMIT) validates the limit param.
    r = admin_client.get(
        "/api/v1/admin/audit/events?limit=0",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 422
    r2 = admin_client.get(
        "/api/v1/admin/audit/events?limit=999",
        headers={"x-api-key": "key-alice"},
    )
    assert r2.status_code == 422


# ---------------------------------------------------------------------------
# /api/v1/admin/quota/usage
# ---------------------------------------------------------------------------


def test_admin_quota_usage_merges_uploads_and_notebooks(admin_client):
    upload_quota: DailyUploadQuota = admin_client.app_obj.state.upload_quota
    upload_quota.check_and_record("alice", 1024)
    upload_quota.check_and_record("bob", 4096)

    _seed_notebook(admin_client.db_path, "alice", 3)
    _seed_notebook(admin_client.db_path, "carol", 2)  # no upload usage

    r = admin_client.get(
        "/api/v1/admin/quota/usage",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by_pid = {row["principal_id"]: row for row in body["rows"]}
    assert by_pid["alice"]["bytes_used"] == 1024
    assert by_pid["alice"]["notebook_count"] == 3
    assert by_pid["bob"]["bytes_used"] == 4096
    assert by_pid["bob"]["notebook_count"] == 0
    assert by_pid["carol"]["bytes_used"] == 0
    assert by_pid["carol"]["notebook_count"] == 2
    assert body["daily_limit"] == upload_quota.daily_limit
    assert body["notebook_max"] == 50


def test_admin_quota_usage_empty_db(admin_client):
    r = admin_client.get(
        "/api/v1/admin/quota/usage",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 200
    assert r.json()["rows"] == []


def test_admin_quota_usage_forbids_non_admin(admin_client):
    r = admin_client.get(
        "/api/v1/admin/quota/usage",
        headers={"x-api-key": "key-bob"},
    )
    assert r.status_code == 403


def test_admin_quota_usage_503_when_auth_disabled(admin_client, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    r = admin_client.get(
        "/api/v1/admin/quota/usage",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 503


def test_admin_quota_usage_503_when_allowlist_empty(admin_client, monkeypatch):
    monkeypatch.delenv(ADMIN_PRINCIPALS_ENV, raising=False)
    r = admin_client.get(
        "/api/v1/admin/quota/usage",
        headers={"x-api-key": "key-alice"},
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Step 7: ADMIN_ACCESS audit events
# ---------------------------------------------------------------------------


def test_admin_access_audit_emitted_on_success(admin_client):
    """Each successful admin request appends an admin.access record."""
    store: AuditStore = admin_client.app_obj.state.audit_store
    admin_client.get("/api/v1/admin/health", headers={"x-api-key": "key-alice"})

    events = store.query_events(event=AuditEvent.ADMIN_ACCESS.value).items
    assert len(events) == 1
    rec = events[0]
    assert rec.principal_id == "alice"
    assert rec.outcome == "success"
    assert rec.resource_type == "admin.endpoint"
    assert rec.resource_id == "/api/v1/admin/health"
    assert rec.http_status == 200


def test_admin_access_audit_includes_path_method(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    admin_client.get(
        "/api/v1/admin/audit/events?limit=5",
        headers={"x-api-key": "key-alice"},
    )
    events = store.query_events(event=AuditEvent.ADMIN_ACCESS.value).items
    assert len(events) == 1
    payload = events[0].payload_json
    assert "GET" in payload
    assert "/api/v1/admin/audit/events" in payload
    assert "admin.method" in payload
    assert "limit" in payload  # query param captured


def test_admin_access_audit_not_emitted_on_403(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    # Non-admin caller — 403. Must NOT produce an admin.access record.
    r = admin_client.get("/api/v1/admin/health", headers={"x-api-key": "key-bob"})
    assert r.status_code == 403
    events = store.query_events(event=AuditEvent.ADMIN_ACCESS.value).items
    assert events == []


def test_admin_access_audit_not_emitted_on_401(admin_client):
    store: AuditStore = admin_client.app_obj.state.audit_store
    r = admin_client.get("/api/v1/admin/health")
    assert r.status_code == 401
    events = store.query_events(event=AuditEvent.ADMIN_ACCESS.value).items
    assert events == []


def test_admin_access_audit_records_per_request(admin_client):
    """Three successful requests → three distinct audit rows."""
    store: AuditStore = admin_client.app_obj.state.audit_store
    for _ in range(3):
        admin_client.get("/api/v1/admin/health", headers={"x-api-key": "key-alice"})

    events = store.query_events(event=AuditEvent.ADMIN_ACCESS.value).items
    assert len(events) == 3
    # All distinct event_ids.
    assert len({e.event_id for e in events}) == 3
