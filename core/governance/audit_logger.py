from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Request

from core.governance.audit_events import AuditEvent
from core.governance.audit_redact import encode_payload, redact
from core.governance.audit_store import AuditRecord, AuditStore
from core.observability.logging_utils import emit_json_log


logger = logging.getLogger("comac.audit")
_SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _extract_remote_addr(request: Request | None) -> str:
    if request is None:
        return "-"

    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()

    client = getattr(request, "client", None)
    if client and getattr(client, "host", None):
        return str(client.host)

    return "-"


def _extract_request_id(request: Request | None) -> str:
    if request is None:
        return str(uuid4())

    state_request_id = getattr(getattr(request, "state", None), "request_id", None)
    if state_request_id:
        return str(state_request_id)

    header_request_id = request.headers.get("x-request-id")
    if header_request_id:
        return header_request_id

    return str(uuid4())


def _normalize_event(event: AuditEvent | str) -> str:
    if isinstance(event, AuditEvent):
        return event.value
    return str(event)


def _mirror_fields(record: AuditRecord) -> dict[str, Any]:
    mirrored = asdict(record)
    # emit_json_log already reserves the top-level "event" envelope field.
    mirrored["audit_event"] = mirrored.pop("event")
    return mirrored


class _SystemAuditLogger:
    def __init__(self, parent: AuditLogger, job_name: str) -> None:
        self._parent = parent
        self._job_name = job_name

    def record(
        self,
        *,
        event: AuditEvent | str,
        outcome: str,
        resource_type: str,
        resource_id: str = "-",
        parent_resource_id: str = "-",
        http_status: int,
        error_code: str = "-",
        payload: dict[str, Any] | None = None,
    ) -> AuditRecord:
        return self._parent.record(
            event=event,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            parent_resource_id=parent_resource_id,
            http_status=http_status,
            error_code=error_code,
            payload=payload,
            principal_id=f"system:{self._job_name}",
            actor_type="system",
        )


class AuditLogger:
    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        *,
        store: AuditStore | None = None,
    ) -> None:
        self.store = store or AuditStore(db_path=db_path)

    def for_system(self, job_name: str) -> _SystemAuditLogger:
        return _SystemAuditLogger(self, job_name)

    def record(
        self,
        *,
        event: AuditEvent | str,
        outcome: str,
        resource_type: str,
        http_status: int,
        request: Request | None = None,
        resource_id: str = "-",
        parent_resource_id: str = "-",
        error_code: str = "-",
        payload: dict[str, Any] | None = None,
        principal_id: str | None = None,
        actor_type: str | None = None,
        request_id: str | None = None,
        remote_addr: str | None = None,
    ) -> AuditRecord:
        resolved_remote_addr = remote_addr or _extract_remote_addr(request)
        resolved_actor_type, resolved_principal_id = self._resolve_actor(
            request=request,
            principal_id=principal_id,
            actor_type=actor_type,
            remote_addr=resolved_remote_addr,
        )
        record = AuditRecord(
            event_id=str(uuid4()),
            ts_utc=_utc_now_iso(),
            event=_normalize_event(event),
            outcome=outcome,
            actor_type=resolved_actor_type,
            principal_id=resolved_principal_id,
            request_id=request_id or _extract_request_id(request),
            remote_addr=resolved_remote_addr,
            resource_type=resource_type,
            resource_id=resource_id,
            parent_resource_id=parent_resource_id,
            http_status=http_status,
            error_code=error_code,
            payload_json=encode_payload(redact(payload)),
            schema_version=_SCHEMA_VERSION,
        )
        self._append_with_fallback(record)
        return record

    def _resolve_actor(
        self,
        *,
        request: Request | None,
        principal_id: str | None,
        actor_type: str | None,
        remote_addr: str,
    ) -> tuple[str, str]:
        if principal_id:
            if actor_type:
                return actor_type, principal_id
            if principal_id.startswith("system:"):
                return "system", principal_id
            if principal_id.startswith("ip:"):
                return "anonymous", principal_id
            return "user", principal_id

        if request is not None:
            principal = getattr(getattr(request, "state", None), "principal", None)
            request_principal_id = getattr(principal, "principal_id", None)
            if request_principal_id:
                return "user", str(request_principal_id)

        return "anonymous", f"ip:{remote_addr}"

    def _append_with_fallback(self, record: AuditRecord) -> None:
        try:
            self.store.append(record)
        except Exception as exc:
            emit_json_log(
                logger,
                "audit_append_failed",
                audit_event=record.event,
                request_id=record.request_id,
                principal_id=record.principal_id,
                error=exc.__class__.__name__,
                error_message=str(exc),
            )
            emit_json_log(logger, "audit", **_mirror_fields(record))
            return

        emit_json_log(logger, "audit", **_mirror_fields(record))
