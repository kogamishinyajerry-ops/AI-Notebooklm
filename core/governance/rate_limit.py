from __future__ import annotations

import contextvars
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits.storage.memory import MemoryStorage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from core.observability.logging_utils import emit_json_log
from core.governance.sqlite_rate_limit_storage import SQLiteFixedWindowStorage


# Per-request admin flag. slowapi's exempt_when signature is () -> bool, so it
# cannot receive the Request; we rely on the auth dep layer to mark the flag
# before the limiter fires.
_is_admin_request: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "comac_rate_limit_is_admin", default=False
)


def mark_admin_request(is_admin: bool) -> None:
    """Called by the auth dep after resolving principal.is_admin."""
    _is_admin_request.set(is_admin)


logger = logging.getLogger("comac.rate_limit")

CHAT_RATE_ENV = "NOTEBOOKLM_CHAT_RATE"
DEFAULT_CHAT_RATE = "30/minute"
DEFAULT_RETRY_AFTER_SECONDS = 60
CHAT_RATE_DIMENSION = "chat_requests"
CHAT_RATE_EXCEEDED_DETAIL = f"Rate limit exceeded: {CHAT_RATE_DIMENSION}"
RATE_LIMIT_DB_PATH_STATE = "rate_limit_db_path"

_RATE_PATTERN = re.compile(r"^\d+/(second|minute|hour|day)s?$", re.IGNORECASE)


def _get_chat_rate() -> str:
    raw = os.getenv(CHAT_RATE_ENV, "").strip()
    if not raw:
        return DEFAULT_CHAT_RATE

    if not _RATE_PATTERN.match(raw):
        logger.warning(
            "%s=%r is invalid; falling back to %s",
            CHAT_RATE_ENV,
            raw,
            DEFAULT_CHAT_RATE,
        )
        return DEFAULT_CHAT_RATE
    return raw


def _principal_key(request: Request) -> str:
    principal = getattr(request.state, "principal", None)
    principal_id = getattr(principal, "principal_id", None)
    if principal_id:
        return f"principal:{principal_id}"
    return f"ip:{get_remote_address(request)}"


def is_admin_exempt() -> bool:
    """slowapi exempt_when callable (zero-arg in slowapi 0.1.9).

    Reads the per-request admin flag set by :func:`mark_admin_request` from
    the auth dep. If the flag was never set (auth disabled, anonymous path),
    returns False so the normal limit applies.
    """
    return _is_admin_request.get()


def _build_rate_limit_payload(
    detail: str,
    retry_after: int = DEFAULT_RETRY_AFTER_SECONDS,
) -> dict[str, int | str]:
    return {"detail": detail, "retry_after": retry_after}


def _normalize_rate_limit_detail(detail: str | None) -> str:
    if not detail:
        return CHAT_RATE_EXCEEDED_DETAIL
    if detail.startswith("Rate limit exceeded: "):
        return detail
    return f"Rate limit exceeded: {detail}"


def rate_limit_exception_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    detail = _normalize_rate_limit_detail(getattr(exc, "detail", None))
    retry_after = DEFAULT_RETRY_AFTER_SECONDS
    return JSONResponse(
        status_code=429,
        content=_build_rate_limit_payload(detail, retry_after),
        headers={"Retry-After": str(retry_after)},
    )


def _detect_worker_count() -> int:
    raw = os.getenv("WEB_CONCURRENCY", "").strip()
    if not raw:
        return 1
    try:
        workers = int(raw)
    except ValueError:
        return 1
    return workers if workers > 0 else 1


def _resolve_rate_limit_db_path(app: FastAPI) -> Path | None:
    value = getattr(app.state, RATE_LIMIT_DB_PATH_STATE, None)
    if value in (None, ""):
        return None
    return Path(value)


def _build_rate_limit_storage(
    app: FastAPI,
    workers: int,
) -> tuple[MemoryStorage | SQLiteFixedWindowStorage, str, Path | None]:
    db_path = _resolve_rate_limit_db_path(app)
    if workers > 1 and db_path is not None:
        return SQLiteFixedWindowStorage(db_path), "sqlite", db_path
    return MemoryStorage(), "memory", db_path


limiter = Limiter(key_func=_principal_key, default_limits=[])


def setup_rate_limit(app: FastAPI) -> None:
    if not getattr(app.state, "_rate_limit_routes_initialized", False):
        limiter._route_limits.clear()
        limiter._dynamic_route_limits.clear()
        marked = getattr(limiter, "_Limiter__marked_for_limiting", None)
        if marked is not None:
            marked.clear()
        app.state._rate_limit_routes_initialized = True

    workers = _detect_worker_count()
    storage, backend, db_path = _build_rate_limit_storage(app, workers)

    # Each app setup gets a fresh limiter storage choice. Default single-worker
    # test apps keep the isolated in-memory semantics, while multi-worker app
    # setups can opt into a shared local SQLite backend by exposing db_path on
    # app.state.
    limiter._storage = storage
    limiter._limiter = type(limiter._limiter)(limiter._storage)
    if getattr(limiter, "_fallback_limiter", None) is not None:
        limiter._fallback_storage = MemoryStorage()
        limiter._fallback_limiter = type(limiter._fallback_limiter)(
            limiter._fallback_storage
        )
    app.state.limiter = limiter
    app.state.rate_limit_backend = backend

    if not getattr(app.state, "_rate_limit_handler_registered", False):
        app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
        app.state._rate_limit_handler_registered = True

    if workers > 1 and not getattr(app.state, "_rate_limit_worker_warned", False):
        effective_chat_rate = _get_chat_rate()
        if backend == "sqlite":
            logger.info(
                "rate_limit.multi_worker_warning: shared SQLite backend enabled for "
                "chat_requests across %s workers at %s",
                workers,
                db_path,
            )
        else:
            logger.warning(
                "rate_limit.multi_worker_warning: MemoryStore is per-process; "
                "effective chat_requests limit is approximately %sx %s",
                workers,
                effective_chat_rate,
            )
        emit_json_log(
            logger,
            "rate_limit.multi_worker_warning",
            workers=workers,
            backend=backend,
            db_path=str(db_path) if db_path is not None else None,
            effective_multiplier=1 if backend == "sqlite" else workers,
            effective_chat_rate=effective_chat_rate,
        )
        app.state._rate_limit_worker_warned = True
