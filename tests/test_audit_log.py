from __future__ import annotations

import sqlite3
from pathlib import Path

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
