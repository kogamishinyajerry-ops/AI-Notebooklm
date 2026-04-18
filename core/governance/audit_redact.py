from __future__ import annotations

import hashlib
import json
from typing import Any


MAX_FIELD_LENGTH = 256
MAX_PAYLOAD_BYTES = 2048

_ALLOWED_FIELDS = {
    "title",
    "space_id",
    "notebook_id",
    "source_id",
    "note_id",
    "source_type",
    "content_type",
    "bytes_size",
    "filename_sha256",
    "ua_sha256",
    "chat.message_length",
    "chat.history_turns",
    "quota.dimension",
    "quota.limit",
    "quota.used",
    "orphan_table",
    "orphan_id",
    "parent_table",
    "parent_column",
    # V4.2-T3: admin.access observability (route path / method / query).
    "admin.method",
    "admin.path",
    "admin.query",
}


def _short_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_FIELD_LENGTH]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)[:MAX_FIELD_LENGTH]


def redact(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}

    sanitized: dict[str, Any] = {}
    filename = raw.get("filename")
    if filename:
        sanitized["filename_sha256"] = _short_sha256(str(filename))

    user_agent = raw.get("user_agent")
    if user_agent:
        sanitized["ua_sha256"] = _short_sha256(str(user_agent))

    for key, value in raw.items():
        if key in {"filename", "user_agent"}:
            continue
        if key not in _ALLOWED_FIELDS:
            continue
        sanitized[key] = _json_safe(value)

    return _truncate_payload(sanitized)


def encode_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return serialized
    return json.dumps(_truncate_payload(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truncate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(payload)
    if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return candidate

    for key, value in list(candidate.items()):
        if isinstance(value, str) and len(value) > 64:
            candidate[key] = value[:64]

    candidate["_truncated"] = True
    if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return candidate

    preserved = {}
    for key in (
        "filename_sha256",
        "ua_sha256",
        "quota.dimension",
        "quota.limit",
        "quota.used",
        "chat.message_length",
        "chat.history_turns",
        "notebook_id",
        "source_id",
        "note_id",
        "space_id",
        "_truncated",
    ):
        if key in candidate:
            preserved[key] = candidate[key]

    if "_truncated" not in preserved:
        preserved["_truncated"] = True
    return preserved
