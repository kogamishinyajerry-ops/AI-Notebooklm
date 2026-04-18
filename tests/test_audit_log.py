from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from core.governance.audit_events import AuditEvent
from core.governance.audit_logger import AuditLogger
from core.governance.audit_redact import encode_payload, redact
from core.governance.audit_store import AuditRecord, AuditStore
from core.storage.sqlite_db import get_connection, init_schema


def _new_db(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


def test_audit_schema_creates_table_and_triggers(tmp_path):
    conn = _new_db(tmp_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'audit_events'"
        ).fetchone()
        assert table is not None

        triggers = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit_events_%'"
            ).fetchall()
        }
        assert triggers == {"audit_events_no_delete", "audit_events_no_update"}

        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_audit_%'"
            ).fetchall()
        }
        assert indexes == {
            "idx_audit_event_ts",
            "idx_audit_principal_ts",
            "idx_audit_resource",
            "idx_audit_ts",
        }
    finally:
        conn.close()


def _insert_audit_row(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (
            event_id,
            ts_utc,
            event,
            outcome,
            actor_type,
            principal_id,
            request_id,
            remote_addr,
            resource_type,
            resource_id,
            parent_resource_id,
            http_status,
            error_code,
            payload_json,
            schema_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "evt-1",
            "2026-04-18T00:00:00+00:00",
            "notebook.create",
            "success",
            "user",
            "alice",
            "req-1",
            "127.0.0.1",
            "notebook",
            "nb-1",
            "-",
            201,
            "-",
            "{}",
            1,
        ),
    )
    conn.commit()


def test_audit_append_is_append_only_update_forbidden(tmp_path):
    conn = _new_db(tmp_path)
    try:
        _insert_audit_row(conn)
        try:
            conn.execute(
                "UPDATE audit_events SET http_status = ? WHERE event_id = ?",
                (500, "evt-1"),
            )
            conn.commit()
            raise AssertionError("UPDATE should have been blocked by trigger")
        except sqlite3.IntegrityError as exc:
            assert "append-only" in str(exc)
    finally:
        conn.close()


def test_audit_append_is_append_only_delete_forbidden(tmp_path):
    conn = _new_db(tmp_path)
    try:
        _insert_audit_row(conn)
        try:
            conn.execute("DELETE FROM audit_events WHERE event_id = ?", ("evt-1",))
            conn.commit()
            raise AssertionError("DELETE should have been blocked by trigger")
        except sqlite3.IntegrityError as exc:
            assert "append-only" in str(exc)
    finally:
        conn.close()


def test_audit_event_enum_is_complete():
    assert [event.value for event in AuditEvent] == [
        "space.create",
        "notebook.create",
        "notebook.delete",
        "source.upload",
        "source.delete",
        "chat.request",
        "chat.history.clear",
        "note.create",
        "note.update",
        "note.delete",
        "studio.create",
        "studio.delete",
        "graph.generate",
        "quota.denied",
        "auth.denied",
    ]


def test_audit_redact_drops_secret_fields():
    payload = redact(
        {
            "title": "Flight Controls",
            "api_key": "secret-key",
            "authorization": "Bearer top-secret",
            "file_content": "super confidential",
            "chat.message_length": 12,
        }
    )

    assert payload == {
        "title": "Flight Controls",
        "chat.message_length": 12,
    }


def test_audit_redact_truncates_long_fields():
    raw = {
        "title": "T" * 500,
        "chat.message_length": 11,
        "quota.dimension": "upload_bytes",
        "quota.limit": 1024,
        "quota.used": 512,
        "notebook_id": "nb-1",
        "source_id": "src-1",
        "note_id": "note-1",
        "space_id": "space-1",
        "content_type": "application/pdf",
        "source_type": "upload",
        "ua_sha256": "u" * 500,
        "filename_sha256": "f" * 500,
    }
    payload = redact(raw)

    assert payload["title"] == "T" * 256
    assert payload["ua_sha256"] == "u" * 256
    assert payload["filename_sha256"] == "f" * 256
    assert encode_payload(payload).encode("utf-8")
    assert len(encode_payload(payload).encode("utf-8")) <= 2048

    oversized_json = encode_payload(
        {
            "title": "T" * 256,
            "space_id": "S" * 256,
            "notebook_id": "N" * 256,
            "source_id": "SRC" * 80,
            "note_id": "NOTE" * 64,
            "source_type": "upload" * 40,
            "content_type": "application/pdf" * 20,
            "filename_sha256": "f" * 256,
            "ua_sha256": "u" * 256,
            "chat.message_length": 11,
            "chat.history_turns": 99,
            "quota.dimension": "upload_bytes" * 20,
            "quota.limit": 1024,
            "quota.used": 1023,
        }
    )
    oversized = json.loads(oversized_json)
    assert oversized["_truncated"] is True
    assert len(oversized_json.encode("utf-8")) <= 2048


def test_audit_redact_hashes_filename():
    payload = redact({"filename": "secret.pdf"})

    assert "filename" not in payload
    assert payload["filename_sha256"] == "29af7f0168d2731e"


def _make_record(*, event_id: str, principal_id: str = "alice", resource_id: str = "nb-1") -> AuditRecord:
    return AuditRecord(
        event_id=event_id,
        ts_utc="2026-04-18T00:00:00.000000+00:00",
        event=AuditEvent.NOTEBOOK_CREATE.value,
        outcome="success",
        actor_type="user",
        principal_id=principal_id,
        request_id=f"req-{event_id}",
        remote_addr="127.0.0.1",
        resource_type="notebook",
        resource_id=resource_id,
        parent_resource_id="-",
        http_status=201,
        error_code="-",
        payload_json='{"title":"Flight Controls"}',
        schema_version=1,
    )


def test_audit_append_persists_all_fields(tmp_path):
    db_path = tmp_path / "audit.db"
    store = AuditStore(db_path=db_path)
    record = _make_record(event_id="evt-persist", resource_id="nb-persist")

    store.append(record)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM audit_events WHERE event_id = ?",
            (record.event_id,),
        ).fetchone()
        assert row is not None
        assert dict(row) == {
            "event_id": record.event_id,
            "ts_utc": record.ts_utc,
            "event": record.event,
            "outcome": record.outcome,
            "actor_type": record.actor_type,
            "principal_id": record.principal_id,
            "request_id": record.request_id,
            "remote_addr": record.remote_addr,
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
            "parent_resource_id": record.parent_resource_id,
            "http_status": record.http_status,
            "error_code": record.error_code,
            "payload_json": record.payload_json,
            "schema_version": record.schema_version,
        }
    finally:
        conn.close()


def test_audit_append_concurrent_writers_no_loss(tmp_path):
    db_path = tmp_path / "audit.db"
    store = AuditStore(db_path=db_path)

    def write_event(index: int) -> None:
        store.append(
            _make_record(
                event_id=f"evt-{index}",
                principal_id=f"user-{index % 4}",
                resource_id=f"nb-{index % 7}",
            )
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(write_event, range(1000)))

    conn = get_connection(db_path)
    try:
        counts = conn.execute(
            """
            SELECT COUNT(*) AS total_count, COUNT(DISTINCT event_id) AS distinct_event_ids
            FROM audit_events
            """
        ).fetchone()
        assert counts["total_count"] == 1000
        assert counts["distinct_event_ids"] == 1000
    finally:
        conn.close()


def _make_request(
    *,
    principal_id: str | None = "alice",
    request_id: str = "req-audit",
    client_ip: str = "127.0.0.1",
    forwarded_for: str | None = None,
) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode("utf-8")))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_ip, 1234),
        "state": {},
    }
    request = Request(scope)
    request.state.request_id = request_id
    if principal_id is not None:
        request.state.principal = SimpleNamespace(principal_id=principal_id)
    return request


def test_audit_logger_mirrors_to_json_log(tmp_path, caplog):
    caplog.set_level("INFO", logger="comac.audit")

    db_path = tmp_path / "audit.db"
    audit_logger = AuditLogger(db_path=db_path)
    request = _make_request(
        principal_id="alice",
        request_id="req-mirror",
        client_ip="127.0.0.1",
        forwarded_for="203.0.113.10",
    )

    record = audit_logger.record(
        request=request,
        event=AuditEvent.NOTEBOOK_CREATE,
        outcome="success",
        resource_type="notebook",
        resource_id="nb-123",
        http_status=201,
        payload={"title": "Flight Controls"},
    )

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM audit_events WHERE event_id = ?",
            (record.event_id,),
        ).fetchone()
        assert row is not None
    finally:
        conn.close()

    audit_logs = [
        json.loads(log_record.getMessage())
        for log_record in caplog.records
        if log_record.name == "comac.audit" and '"event": "audit"' in log_record.getMessage()
    ]
    assert len(audit_logs) == 1
    audit_log = audit_logs[0]

    expected_fields = dict(row)
    expected_fields["audit_event"] = expected_fields.pop("event")

    assert audit_log["event"] == "audit"
    for key, value in expected_fields.items():
        assert audit_log[key] == value


def test_audit_sqlite_failure_falls_back_to_json_log(caplog):
    caplog.set_level("INFO", logger="comac.audit")

    class _FailingStore:
        def append(self, record):
            raise sqlite3.OperationalError("disk full")

    audit_logger = AuditLogger(store=_FailingStore())
    app = FastAPI()

    @app.post("/ok")
    def ok_route(request: Request):
        audit_logger.record(
            request=request,
            event=AuditEvent.NOTEBOOK_CREATE,
            outcome="success",
            resource_type="notebook",
            resource_id="nb-ok",
            http_status=200,
            payload={"title": "Fallback"},
        )
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/ok", headers={"x-request-id": "req-fallback"})

    assert response.status_code == 200
    log_events = [
        json.loads(log_record.getMessage())["event"]
        for log_record in caplog.records
        if log_record.name == "comac.audit"
    ]
    assert "audit" in log_events
    assert "audit_append_failed" in log_events
