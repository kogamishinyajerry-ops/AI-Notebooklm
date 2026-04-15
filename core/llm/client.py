import ipaddress
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

# Load local runtime configuration from .env when present.
load_dotenv()


@dataclass(frozen=True)
class LocalLLMConfig:
    """Runtime configuration for the local OpenAI-compatible inference server."""

    base_url: str
    model: str
    timeout: float
    api_key: Optional[str] = None


def _is_private_or_local_host(hostname: Optional[str]) -> bool:
    if not hostname:
        return False

    normalized = hostname.lower()
    if normalized in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}:
        return True

    try:
        return ipaddress.ip_address(normalized).is_private
    except ValueError:
        # Keep the rule intentionally strict: only localhost / private IPs / docker bridge.
        return normalized.endswith(".local")


def _normalize_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid LOCAL_LLM_BASE_URL: {base_url}")

    if not _is_private_or_local_host(parsed.hostname):
        raise ValueError(
            f"Public LLM endpoint is forbidden by C1: {parsed.hostname}"
        )

    return base_url.rstrip("/")


def _chat_completions_url(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _build_headers(config: LocalLLMConfig) -> dict:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers


def _build_payload(config: LocalLLMConfig, system_prompt: str, user_query: str, *, stream: bool) -> dict:
    return {
        "model": config.model,
        "temperature": 0,
        "max_tokens": 2048,
        "stream": stream,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
    }


def _extract_text_from_completion(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)

    return ""


def resolve_local_llm_config() -> LocalLLMConfig:
    base_url = (
        os.getenv("LOCAL_LLM_BASE_URL")
        or os.getenv("VLLM_URL")
        or "http://127.0.0.1:8001/v1"
    )
    model = os.getenv("LOCAL_LLM_MODEL", "Qwen2.5-14B-Instruct")
    timeout = float(os.getenv("LOCAL_LLM_TIMEOUT", "60"))
    api_key = os.getenv("LOCAL_LLM_API_KEY")

    return LocalLLMConfig(
        base_url=_normalize_base_url(base_url),
        model=model,
        timeout=timeout,
        api_key=api_key,
    )


def call_local_llm(system_prompt: str, user_query: str) -> str:
    """
    Unified offline LLM interface.
    C1 requires the runtime endpoint to stay on localhost / private network only.
    """
    config = resolve_local_llm_config()
    payload = _build_payload(config, system_prompt, user_query, stream=False)

    try:
        with httpx.Client(timeout=config.timeout) as client:
            response = client.post(
                _chat_completions_url(config.base_url),
                headers=_build_headers(config),
                json=payload,
            )
            response.raise_for_status()
            text = _extract_text_from_completion(response.json())
            if not text:
                raise RuntimeError("empty response from local LLM")
            return text
    except Exception as exc:
        raise RuntimeError(f"Local LLM request failed: {exc}") from exc


async def stream_local_llm(system_prompt: str, user_query: str) -> AsyncIterator[str]:
    """Stream tokens from the local OpenAI-compatible endpoint."""
    config = resolve_local_llm_config()
    payload = _build_payload(config, system_prompt, user_query, stream=True)

    try:
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            async with client.stream(
                "POST",
                _chat_completions_url(config.base_url),
                headers=_build_headers(config),
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    raw = line[5:].strip()
                    if raw in ("", "[DONE]"):
                        continue

                    event = json.loads(raw)
                    choices = event.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if isinstance(content, str) and content:
                        yield content
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                                yield item["text"]
    except Exception as exc:
        raise RuntimeError(f"Local LLM stream failed: {exc}") from exc
