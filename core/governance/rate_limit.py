from __future__ import annotations

import logging
import os
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits.storage.memory import MemoryStorage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from core.observability.logging_utils import emit_json_log


logger = logging.getLogger("comac.rate_limit")

CHAT_RATE_ENV = "NOTEBOOKLM_CHAT_RATE"
DEFAULT_CHAT_RATE = "30/minute"
DEFAULT_RETRY_AFTER_SECONDS = 60
CHAT_RATE_DIMENSION = "chat_requests"
CHAT_RATE_EXCEEDED_DETAIL = f"Rate limit exceeded: {CHAT_RATE_DIMENSION}"

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


limiter = Limiter(key_func=_principal_key, default_limits=[])


def setup_rate_limit(app: FastAPI) -> None:
    if not getattr(app.state, "_rate_limit_routes_initialized", False):
        limiter._route_limits.clear()
        limiter._dynamic_route_limits.clear()
        marked = getattr(limiter, "_Limiter__marked_for_limiting", None)
        if marked is not None:
            marked.clear()
        app.state._rate_limit_routes_initialized = True

    # Each app setup gets a fresh in-memory bucket store. Replacing the storage object,
    # rather than resetting the existing one, prevents lingering TestClient/app instances
    # from sharing chat buckets during full-suite execution.
    limiter._storage = MemoryStorage()
    limiter._limiter = type(limiter._limiter)(limiter._storage)
    if getattr(limiter, "_fallback_limiter", None) is not None:
        limiter._fallback_storage = MemoryStorage()
        limiter._fallback_limiter = type(limiter._fallback_limiter)(
            limiter._fallback_storage
        )
    app.state.limiter = limiter

    if not getattr(app.state, "_rate_limit_handler_registered", False):
        app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
        app.state._rate_limit_handler_registered = True

    workers = _detect_worker_count()
    if workers > 1 and not getattr(app.state, "_rate_limit_worker_warned", False):
        effective_chat_rate = _get_chat_rate()
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
            effective_multiplier=workers,
            effective_chat_rate=effective_chat_rate,
        )
        app.state._rate_limit_worker_warned = True
