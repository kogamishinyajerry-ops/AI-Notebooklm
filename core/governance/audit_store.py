from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditRecord:
    event_id: str
    ts_utc: str
    event: str
    outcome: str
    actor_type: str
    principal_id: str
    request_id: str
    remote_addr: str
    resource_type: str
    resource_id: str
    parent_resource_id: str
    http_status: int
    error_code: str
    payload_json: str
    schema_version: int = 1


def _open_connection(db_path: Path):
    from core.storage.sqlite_db import get_connection, init_schema

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class AuditStore:
    def __init__(self, db_path: str | Path = Path("data/notebooks.db")) -> None:
        self.db_path = Path(db_path)

    def append(self, record: AuditRecord) -> None:
        conn = _open_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
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
                    record.event_id,
                    record.ts_utc,
                    record.event,
                    record.outcome,
                    record.actor_type,
                    record.principal_id,
                    record.request_id,
                    record.remote_addr,
                    record.resource_type,
                    record.resource_id,
                    record.parent_resource_id,
                    record.http_status,
                    record.error_code,
                    record.payload_json,
                    record.schema_version,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
