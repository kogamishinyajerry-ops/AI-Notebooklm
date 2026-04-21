from __future__ import annotations

import ipaddress
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_LLM_PROVIDER = "local"
DEFAULT_VLLM_URL = "http://localhost:8001/v1"
DEFAULT_LOCAL_LLM_MODEL = "qwen-2.5"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/anthropic"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
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
class LLMConfig:
    provider: str
    base_url: str
    origin: str
    model_name: str
    host: str
    scheme: str
    path: str
    port: int | None
    is_private_network: bool
    api_key: str | None = None
    is_external_validation: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("api_key", None)
        return payload

    def build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider == "minimax":
            headers["anthropic-version"] = DEFAULT_ANTHROPIC_VERSION
            if self.api_key:
                headers["x-api-key"] = self.api_key
            return headers
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


LocalLLMConfig = LLMConfig


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


def _current_provider() -> str:
    return os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower() or DEFAULT_LLM_PROVIDER


def _normalize_path(parsed_path: str) -> str:
    path = (parsed_path or "").rstrip("/")
    if path and not path.startswith("/"):
        path = f"/{path}"
    return path


def get_llm_settings_snapshot() -> dict[str, Any]:
    provider = _current_provider()

    if provider == "minimax":
        raw_url = os.getenv("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL).strip() or DEFAULT_MINIMAX_BASE_URL
        model_name = os.getenv("MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL).strip() or DEFAULT_MINIMAX_MODEL
        return {
            "provider": "minimax",
            "configured_url": raw_url.rstrip("/"),
            "model_name": model_name,
            "is_external_validation": True,
        }

    raw_url = os.getenv("VLLM_URL", DEFAULT_VLLM_URL).strip() or DEFAULT_VLLM_URL
    model_name = os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL).strip() or DEFAULT_LOCAL_LLM_MODEL
    return {
        "provider": provider,
        "configured_url": raw_url.rstrip("/"),
        "model_name": model_name,
        "is_external_validation": False,
    }


def _parse_config(raw_url: str, model_name: str, *, provider: str, api_key: str | None, is_external_validation: bool) -> LLMConfig:
    raw_url = raw_url.rstrip("/")
    model_name = model_name.strip()

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise LLMConfigurationError(
            f"{provider.upper()} base URL must use http or https, got: {raw_url}"
        )
    if not parsed.hostname:
        raise LLMConfigurationError(
            f"{provider.upper()} base URL must include a hostname, got: {raw_url}"
        )

    is_private_network = _is_private_host(parsed.hostname)
    if provider == "local" and not is_private_network and not _flag("ALLOW_REMOTE_VLLM", default=False):
        raise LLMConfigurationError(
            "VLLM_URL must point to a localhost/private-network inference service "
            "unless ALLOW_REMOTE_VLLM=1 is explicitly set."
        )

    return LLMConfig(
        provider=provider,
        base_url=raw_url,
        origin=f"{parsed.scheme}://{parsed.netloc}",
        model_name=model_name,
        host=parsed.hostname,
        scheme=parsed.scheme,
        path=_normalize_path(parsed.path),
        port=parsed.port,
        is_private_network=is_private_network,
        api_key=api_key,
        is_external_validation=is_external_validation,
    )


def get_llm_config() -> LLMConfig:
    provider = _current_provider()

    if provider == "local":
        return _parse_config(
            raw_url=os.getenv("VLLM_URL", DEFAULT_VLLM_URL).strip() or DEFAULT_VLLM_URL,
            model_name=os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL).strip() or DEFAULT_LOCAL_LLM_MODEL,
            provider="local",
            api_key=None,
            is_external_validation=False,
        )

    if provider == "minimax":
        api_key = os.getenv("MINIMAX_API_KEY", "").strip()
        if not api_key:
            raise LLMConfigurationError(
                "MINIMAX_API_KEY is required when LLM_PROVIDER=minimax."
            )
        return _parse_config(
            raw_url=os.getenv("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL).strip() or DEFAULT_MINIMAX_BASE_URL,
            model_name=os.getenv("MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL).strip() or DEFAULT_MINIMAX_MODEL,
            provider="minimax",
            api_key=api_key,
            is_external_validation=True,
        )

    raise LLMConfigurationError(
        "LLM_PROVIDER must be one of: local, minimax."
    )


def get_local_llm_config() -> LocalLLMConfig:
    return get_llm_config()


def _base_probe_payload(config: LLMConfig, *, timeout: float) -> dict[str, Any]:
    return {
        "provider": config.provider,
        "model_name": config.model_name,
        "configured_url": config.base_url,
        "origin": config.origin,
        "probe_timeout_seconds": timeout,
        "is_private_network": config.is_private_network,
        "is_external_validation": config.is_external_validation,
    }


def _anthropic_messages_url(config: LLMConfig) -> str:
    if config.base_url.endswith("/v1"):
        return f"{config.base_url}/messages"
    return f"{config.base_url}/v1/messages"


def _anthropic_messages_payload(
    *,
    config: LLMConfig,
    system_prompt: str,
    user_query: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "model": config.model_name,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_query,
                    }
                ],
            }
        ],
    }


def _raise_for_status_with_body(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        body = (response.text or "").strip()
        if len(body) > 600:
            body = f"{body[:600]}..."
        suffix = f"; response_body={body}" if body else ""
        raise requests.HTTPError(f"{exc}{suffix}", response=response) from exc


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    text_blocks: list[str] = []
    for block in payload.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            text_blocks.append(str(block["text"]))
    if text_blocks:
        return "\n".join(text_blocks)
    raise LLMConfigurationError("MiniMax Anthropic response did not include a text block.")


def probe_local_llm(timeout: float = 2.0) -> dict[str, Any]:
    config = get_llm_config()

    if config.provider == "minimax":
        probe_url = _anthropic_messages_url(config)
        try:
            response = requests.post(
                probe_url,
                headers=config.build_headers(),
                json=_anthropic_messages_payload(
                    config=config,
                    system_prompt="You are a health-check assistant.",
                    user_query="Reply with ok.",
                    max_tokens=4,
                ),
                timeout=timeout,
            )
            _raise_for_status_with_body(response)
            payload = response.json()
        except Exception as exc:
            return {
                **_base_probe_payload(config, timeout=timeout),
                "status": "unreachable",
                "available": False,
                "reachable": False,
                "probe_url": probe_url,
                "probe_method": "POST",
                "unavailable_reason": str(exc),
                "error": str(exc),
            }

        return {
            **_base_probe_payload(config, timeout=timeout),
            "status": "ok",
            "available": True,
            "reachable": True,
            "probe_url": probe_url,
            "probe_method": "POST",
            "status_code": response.status_code,
            "response_id": payload.get("id"),
        }

    probe_url = f"{config.base_url}/models"

    try:
        request_kwargs: dict[str, Any] = {"timeout": timeout}
        headers = config.build_headers()
        if headers.get("Authorization"):
            request_kwargs["headers"] = headers
        response = requests.get(probe_url, **request_kwargs)
        _raise_for_status_with_body(response)
        payload = response.json()
    except Exception as exc:
        health_payload = None
        if config.provider == "local":
            try:
                health_response = requests.get(f"{config.origin}/health", timeout=timeout)
                health_response.raise_for_status()
                health_payload = health_response.json()
            except Exception:
                health_payload = None

        if config.provider == "local" and health_payload is not None:
            return {
                **_base_probe_payload(config, timeout=timeout),
                "status": "mismatched_service",
                "available": False,
                "reachable": False,
                "probe_url": probe_url,
                "unavailable_reason": (
                    "The configured endpoint is reachable, but it does not expose "
                    "the expected OpenAI-compatible /v1/models route."
                ),
                "error": (
                    "The configured endpoint is reachable, but it does not expose "
                    "the expected OpenAI-compatible /v1/models route."
                ),
                "health_payload": health_payload,
            }

        return {
            **_base_probe_payload(config, timeout=timeout),
            "status": "unreachable",
            "available": False,
            "reachable": False,
            "probe_url": probe_url,
            "unavailable_reason": str(exc),
            "error": str(exc),
        }

    models = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))

    return {
        **_base_probe_payload(config, timeout=timeout),
        "status": "ok",
        "available": True,
        "reachable": True,
        "probe_url": probe_url,
        "status_code": response.status_code,
        "models": models,
        "model_count": len(models),
    }


def invoke_llm(system_prompt: str, user_query: str, timeout: float = 30.0) -> str:
    config = get_llm_config()
    if config.provider == "minimax":
        response = requests.post(
            _anthropic_messages_url(config),
            headers=config.build_headers(),
            json=_anthropic_messages_payload(
                config=config,
                system_prompt=system_prompt,
                user_query=user_query,
                max_tokens=2000,
            ),
            timeout=timeout,
        )
        _raise_for_status_with_body(response)
        return _extract_anthropic_text(response.json())

    response = requests.post(
        f"{config.base_url}/chat/completions",
        headers=config.build_headers(),
        json={
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ],
        },
        timeout=timeout,
    )
    _raise_for_status_with_body(response)
    return response.json()["choices"][0]["message"]["content"]
