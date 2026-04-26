"""V4.2-T3 Step 6: admin API routes.

Three read-only endpoints for the admin dashboard, all gated by
:func:`core.governance.admin.require_admin` (401/403/503 ladder there).

- GET /api/v1/admin/health           — liveness + env configuration summary
- GET /api/v1/admin/audit/events     — cursor-paginated audit log view
- GET /api/v1/admin/quota/usage      — per-principal upload + notebook snapshot

The routes deliberately do NOT expose write operations — admin in T3 is a
read-only observability role (FD-10). State mutation stays on normal routes
that admins can still call. V4.3 W-V43-15 (PR54-1) tightened the runtime
policy so admin principals only get quota/rate-limit bypass on this admin
router surface (``ADMIN_PATH_PREFIX``), not on ordinary user-facing routes.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.governance.admin import (
    ADMIN_PATH_PREFIX,
    get_admin_principal_ids,
    require_admin,
)
from core.governance.audit_store import AuditStore, MAX_QUERY_LIMIT
from core.governance.quota_store import DailyUploadQuota, NotebookCountCap
from core.security.auth import AuthPrincipal, auth_is_enabled


# Strip the trailing slash from ADMIN_PATH_PREFIX since FastAPI mounts the
# router at this prefix and appends path components (e.g. "/health"). This
# mechanical link guarantees that if the admin route surface ever moves,
# `is_admin_path` and the actual mounted prefix cannot drift apart.
router = APIRouter(prefix=ADMIN_PATH_PREFIX.rstrip("/"), tags=["admin"])

# Recorded at import time — close enough for a lightweight liveness endpoint.
_START_TIME = time.time()


def _get_audit_store(request: Request) -> AuditStore:
    store = getattr(request.app.state, "audit_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Audit store not initialized")
    return store


def _get_upload_quota(request: Request) -> DailyUploadQuota:
    store = getattr(request.app.state, "upload_quota", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Upload quota store not initialized")
    return store


def _get_notebook_cap(request: Request) -> NotebookCountCap:
    cap = getattr(request.app.state, "notebook_cap", None)
    if cap is None:
        raise HTTPException(status_code=503, detail="Notebook cap store not initialized")
    return cap


@router.get("/health")
def admin_health(
    principal: AuthPrincipal = Depends(require_admin),
) -> dict:
    admin_ids = get_admin_principal_ids()
    return {
        "status": "ok",
        "uptime_sec": int(time.time() - _START_TIME),
        "auth_enabled": auth_is_enabled(),
        "admin_count": len(admin_ids),
        "caller": {"principal_id": principal.principal_id, "is_admin": True},
    }


@router.get("/audit/events")
def admin_audit_events(
    request: Request,
    principal: AuthPrincipal = Depends(require_admin),
    event: Optional[str] = Query(default=None),
    principal_id: Optional[str] = Query(default=None),
    outcome: Optional[str] = Query(default=None),
    from_ts: Optional[str] = Query(default=None),
    to_ts: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_QUERY_LIMIT),
    cursor: Optional[str] = Query(default=None),
) -> dict:
    store = _get_audit_store(request)
    try:
        result = store.query_events(
            event=event,
            principal_id=principal_id,
            outcome=outcome,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "items": [
            {
                "event_id": r.event_id,
                "ts_utc": r.ts_utc,
                "event": r.event,
                "outcome": r.outcome,
                "actor_type": r.actor_type,
                "principal_id": r.principal_id,
                "request_id": r.request_id,
                "remote_addr": r.remote_addr,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "parent_resource_id": r.parent_resource_id,
                "http_status": r.http_status,
                "error_code": r.error_code,
                "payload_json": r.payload_json,
            }
            for r in result.items
        ],
        "next_cursor": result.next_cursor,
    }


@router.get("/quota/usage")
def admin_quota_usage(
    request: Request,
    principal: AuthPrincipal = Depends(require_admin),
    usage_date: Optional[str] = Query(default=None),
) -> dict:
    upload_quota = _get_upload_quota(request)
    notebook_cap = _get_notebook_cap(request)

    upload_rows = upload_quota.snapshot_all_principals(usage_date=usage_date)
    notebook_rows = notebook_cap.snapshot_all_principals()

    # Merge into a per-principal view so the dashboard can render one table.
    by_pid: dict[str, dict] = {}
    for row in upload_rows:
        by_pid[row["principal_id"]] = {
            "principal_id": row["principal_id"],
            "usage_date": row["usage_date"],
            "bytes_used": row["bytes_used"],
            "daily_limit": row["daily_limit"],
            "notebook_count": 0,
            "notebook_max": notebook_cap.max_count,
        }
    for row in notebook_rows:
        entry = by_pid.setdefault(
            row["principal_id"],
            {
                "principal_id": row["principal_id"],
                "usage_date": None,
                "bytes_used": 0,
                "daily_limit": upload_quota.daily_limit,
                "notebook_count": 0,
                "notebook_max": notebook_cap.max_count,
            },
        )
        entry["notebook_count"] = row["count"]
        entry["notebook_max"] = row["max_count"]

    rows = sorted(
        by_pid.values(),
        key=lambda r: (r["bytes_used"], r["notebook_count"]),
        reverse=True,
    )
    return {
        "rows": rows,
        "daily_limit": upload_quota.daily_limit,
        "notebook_max": notebook_cap.max_count,
    }
