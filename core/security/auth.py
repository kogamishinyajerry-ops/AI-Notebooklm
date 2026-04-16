from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException, Request


API_KEYS_ENV = "NOTEBOOKLM_API_KEYS"


@dataclass(frozen=True)
class AuthPrincipal:
    principal_id: str


def _parse_registry(raw: str) -> Dict[str, AuthPrincipal]:
    raw = raw.strip()
    if not raw:
        return {}

    if raw.startswith("{"):
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{API_KEYS_ENV} JSON value must be an object")
        return {
            str(api_key).strip(): AuthPrincipal(principal_id=str(principal_id).strip())
            for principal_id, api_key in data.items()
            if str(api_key).strip() and str(principal_id).strip()
        }

    registry: Dict[str, AuthPrincipal] = {}
    for item in raw.split(","):
        pair = item.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError(
                f"{API_KEYS_ENV} entries must use 'principal_id:api_key' format"
            )
        principal_id, api_key = pair.split(":", 1)
        principal_id = principal_id.strip()
        api_key = api_key.strip()
        if not principal_id or not api_key:
            continue
        registry[api_key] = AuthPrincipal(principal_id=principal_id)
    return registry


def get_api_key_registry() -> Dict[str, AuthPrincipal]:
    raw = os.getenv(API_KEYS_ENV, "").strip()
    if not raw:
        return {}
    try:
        return _parse_registry(raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def auth_is_enabled() -> bool:
    return bool(os.getenv(API_KEYS_ENV, "").strip())


def _extract_api_key(request: Request) -> Optional[str]:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def get_current_principal(request: Request) -> Optional[AuthPrincipal]:
    registry = get_api_key_registry()
    if not registry:
        return None

    api_key = _extract_api_key(request)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    principal = registry.get(api_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return principal
