from __future__ import annotations

import ipaddress
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_VLLM_URL = "http://localhost:8001/v1"
DEFAULT_LOCAL_LLM_MODEL = "qwen-2.5"
_ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
_ALLOWED_LOCAL_SUFFIXES = (
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".corp",
    ".localdomain",
)


class LLMConfigurationError(RuntimeError):
    """Raised when the configured local LLM endpoint is unsafe or invalid."""


@dataclass(frozen=True)
class LocalLLMConfig:
    base_url: str
    model_name: str
    host: str
    scheme: str
    path: str
    port: int | None
    is_private_network: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_private_host(host: str) -> bool:
    normalized = host.strip().lower()
    if not normalized:
        return False
    if normalized in _ALLOWED_LOCAL_HOSTS:
        return True
    if normalized.endswith(_ALLOWED_LOCAL_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def get_local_llm_config() -> LocalLLMConfig:
    raw_url = os.getenv("VLLM_URL", DEFAULT_VLLM_URL).strip()
    model_name = os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL).strip() or DEFAULT_LOCAL_LLM_MODEL

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise LLMConfigurationError(
            f"VLLM_URL must use http or https, got: {raw_url}"
        )
    if not parsed.hostname:
        raise LLMConfigurationError(
            f"VLLM_URL must include a hostname, got: {raw_url}"
        )

    is_private_network = _is_private_host(parsed.hostname)
    if not is_private_network and not _flag("ALLOW_REMOTE_VLLM", default=False):
        raise LLMConfigurationError(
            "VLLM_URL must point to a localhost/private-network inference service "
            "unless ALLOW_REMOTE_VLLM=1 is explicitly set."
        )

    path = (parsed.path or "").rstrip("/")
    if path and not path.startswith("/"):
        path = f"/{path}"

    return LocalLLMConfig(
        base_url=raw_url.rstrip("/"),
        model_name=model_name,
        host=parsed.hostname,
        scheme=parsed.scheme,
        path=path or "",
        port=parsed.port,
        is_private_network=is_private_network,
    )


def probe_local_llm(timeout: float = 2.0) -> dict[str, Any]:
    config = get_local_llm_config()
    probe_url = f"{config.base_url}/models"

    try:
        response = requests.get(probe_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "status": "unreachable",
            "reachable": False,
            "probe_url": probe_url,
            "configured_url": config.base_url,
            "model_name": config.model_name,
            "is_private_network": config.is_private_network,
            "error": str(exc),
        }

    models = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))

    return {
        "status": "ok",
        "reachable": True,
        "probe_url": probe_url,
        "configured_url": config.base_url,
        "model_name": config.model_name,
        "is_private_network": config.is_private_network,
        "status_code": response.status_code,
        "models": models,
        "model_count": len(models),
    }
