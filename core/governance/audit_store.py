from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Cursor-paginated read API — see tests/test_audit_query.py for contract.
DEFAULT_QUERY_LIMIT = 50
MAX_QUERY_LIMIT = 200


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


@dataclass(frozen=True)
class AuditQueryResult:
    items: List[AuditRecord] = field(default_factory=list)
    next_cursor: Optional[str] = None


def _encode_cursor(ts_utc: str, event_id: str) -> str:
    payload = json.dumps({"ts": ts_utc, "id": event_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid cursor: {exc}") from exc
    if not isinstance(data, dict) or "ts" not in data or "id" not in data:
        raise ValueError("invalid cursor: missing ts/id")
    return str(data["ts"]), str(data["id"])


def _initialize_db(db_path: Path) -> None:
    from core.storage.sqlite_db import get_connection, init_schema

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        init_schema(conn)
    finally:
        conn.close()


def _open_connection(db_path: Path):
    from core.storage.sqlite_db import get_connection

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return get_connection(db_path)


class AuditStore:
    def __init__(self, db_path: str | Path = Path("data/notebooks.db")) -> None:
        self.db_path = Path(db_path)
        _initialize_db(self.db_path)

    _INSERT_SQL = """
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
    """

    @staticmethod
    def _record_params(record: AuditRecord) -> tuple:
        return (
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
        )

    def append(self, record: AuditRecord) -> None:
        conn = _open_connection(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(self._INSERT_SQL, self._record_params(record))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def append_within(self, conn, record: AuditRecord) -> None:
        """INSERT a record on a caller-owned connection.

        No BEGIN / COMMIT / CLOSE — the caller owns the transaction. Use
        when the audit row MUST be atomic with other writes in the same
        transaction (e.g. V4.2-T4 notebook ownership migration, where
        losing the audit row would break the compliance evidence chain).
        """
        conn.execute(self._INSERT_SQL, self._record_params(record))

    def query_events(
        self,
        *,
        event: Optional[str] = None,
        principal_id: Optional[str] = None,
        outcome: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        cursor: Optional[str] = None,
    ) -> AuditQueryResult:
        """Cursor-paginated read over audit_events.

        Ordering: (ts_utc DESC, event_id DESC) — stable under equal timestamps.
        Cursor is opaque; callers must pass through unchanged.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        effective_limit = min(limit, MAX_QUERY_LIMIT)

        where: list[str] = []
        params: list[object] = []
        if event is not None:
            where.append("event = ?")
            params.append(event)
        if principal_id is not None:
            where.append("principal_id = ?")
            params.append(principal_id)
        if outcome is not None:
            where.append("outcome = ?")
            params.append(outcome)
        if from_ts is not None:
            where.append("ts_utc >= ?")
            params.append(from_ts)
        if to_ts is not None:
            where.append("ts_utc < ?")
            params.append(to_ts)

        if cursor is not None:
            cur_ts, cur_id = _decode_cursor(cursor)
            # Strict lexicographic tuple comparison (ts, id) < (cur_ts, cur_id).
            where.append("(ts_utc < ? OR (ts_utc = ? AND event_id < ?))")
            params.extend([cur_ts, cur_ts, cur_id])

        sql = (
            "SELECT event_id, ts_utc, event, outcome, actor_type, principal_id, "
            "request_id, remote_addr, resource_type, resource_id, parent_resource_id, "
            "http_status, error_code, payload_json, schema_version "
            "FROM audit_events"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts_utc DESC, event_id DESC LIMIT ?"
        params.append(effective_limit + 1)  # fetch one extra to detect has_more

        conn = _open_connection(self.db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        has_more = len(rows) > effective_limit
        rows = rows[:effective_limit]
        items = [
            AuditRecord(
                event_id=row["event_id"],
                ts_utc=row["ts_utc"],
                event=row["event"],
                outcome=row["outcome"],
                actor_type=row["actor_type"],
                principal_id=row["principal_id"],
                request_id=row["request_id"],
                remote_addr=row["remote_addr"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                parent_resource_id=row["parent_resource_id"],
                http_status=row["http_status"],
                error_code=row["error_code"],
                payload_json=row["payload_json"],
                schema_version=row["schema_version"],
            )
            for row in rows
        ]
        next_cursor = (
            _encode_cursor(items[-1].ts_utc, items[-1].event_id) if has_more and items else None
        )
        return AuditQueryResult(items=items, next_cursor=next_cursor)
