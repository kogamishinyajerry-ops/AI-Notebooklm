"""V4.2-T3: admin role resolution.

Admin identity is sourced exclusively from the ``NOTEBOOKLM_ADMIN_PRINCIPALS``
environment variable (comma-separated principal ids). Admins are a strict
subset of principals already registered in ``NOTEBOOKLM_API_KEYS`` — admin
status never bypasses authentication, only quota/rate-limit dimensions.

Design choices (FD-1 / FD-9 / FD-10 from the T3 frozen pack):

- env-only allowlist; no header claims / JWT / OAuth (C1 zero-new-dep)
- binary is_admin (no role hierarchy in T3)
- admins still require a valid API key present in NOTEBOOKLM_API_KEYS
- malformed entries are warned and skipped, never crash (fail-closed)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Set

from fastapi import HTTPException, Request


if TYPE_CHECKING:
    from core.security.auth import AuthPrincipal


logger = logging.getLogger("comac.governance.admin")

ADMIN_PRINCIPALS_ENV = "NOTEBOOKLM_ADMIN_PRINCIPALS"


def _parse_admin_list(raw: str) -> Set[str]:
    result: Set[str] = set()
    for raw_item in raw.split(","):
        pid = raw_item.strip()
        if not pid:
            continue
        if any(ch.isspace() for ch in pid):
            logger.warning(
                "%s entry contains internal whitespace and was skipped as invalid: %r",
                ADMIN_PRINCIPALS_ENV,
                pid,
            )
            continue
        result.add(pid)
    return result


def get_admin_principal_ids() -> Set[str]:
    """Return the set of principal ids configured as admins.

    Reads env on every call (no module-level cache) so that tests and
    reload scenarios observe the current value. The cost is negligible
    compared to the request pipeline.
    """
    raw = os.getenv(ADMIN_PRINCIPALS_ENV, "")
    if not raw or not raw.strip():
        return set()
    return _parse_admin_list(raw)


def resolve_admin(principal_id: str) -> bool:
    """Return True iff ``principal_id`` is configured as an admin.

    Empty / falsy principal_id is always non-admin — defends against an
    accidental empty string in the allowlist being treated as a wildcard.
    """
    if not principal_id:
        return False
    return principal_id in get_admin_principal_ids()


def require_admin(request: Request) -> "AuthPrincipal":
    """FastAPI dependency: gate a route to admin-only access.

    Response codes (stable, covered by tests T5-T7):

    * 503 — auth is not enabled (no API key registry configured)
    * 503 — admin allowlist is empty (NOTEBOOKLM_ADMIN_PRINCIPALS unset)
    * 401 — missing / invalid API key (delegated to ``get_current_principal``)
    * 403 — authenticated but principal is not in the admin allowlist
    * 200 — returns the enriched ``AuthPrincipal`` with ``is_admin=True``

    Admin is a *strict extension* of auth: admin never bypasses auth, only
    quota/rate-limit dimensions (FD-10).
    """
    # Lazy import to avoid circular dependency (auth -> admin for enrichment,
    # admin -> auth for the dependency chain).
    from core.security.auth import auth_is_enabled, get_current_principal

    if not auth_is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Admin requires API key auth; NOTEBOOKLM_API_KEYS is not configured",
        )
    if not get_admin_principal_ids():
        raise HTTPException(
            status_code=503,
            detail="Admin not configured; NOTEBOOKLM_ADMIN_PRINCIPALS is empty",
        )

    principal = get_current_principal(request)
    if principal is None:
        # Defense-in-depth: auth_is_enabled() true but registry empty shouldn't happen;
        # get_current_principal already raises 401 for missing/invalid keys.
        raise HTTPException(status_code=401, detail="API key required")
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return principal
