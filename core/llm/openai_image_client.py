from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urljoin

import requests

from core.llm.media_types import GeneratedMedia


DEFAULT_OPENAI_IMAGE_BASE_URL = "https://api.openai.com"
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_OPENAI_IMAGE_SIZE = "1536x1024"
DEFAULT_OPENAI_IMAGE_QUALITY = "medium"
DEFAULT_OPENAI_IMAGE_TIMEOUT = 120.0


class OpenAIImageError(RuntimeError):
    """Raised when OpenAI image generation cannot produce a usable asset."""


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _timeout() -> float:
    value = os.getenv("OPENAI_IMAGE_TIMEOUT", "").strip()
    if not value:
        return DEFAULT_OPENAI_IMAGE_TIMEOUT
    try:
        return float(value)
    except ValueError as exc:
        raise OpenAIImageError("OPENAI_IMAGE_TIMEOUT must be a number.") from exc


def _api_key() -> str:
    api_key = (
        os.getenv("OPENAI_IMAGE_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        raise OpenAIImageError("OPENAI_API_KEY or OPENAI_IMAGE_API_KEY is required for OpenAI image generation.")
    return api_key


def _base_url() -> str:
    return _env("OPENAI_IMAGE_BASE_URL", DEFAULT_OPENAI_IMAGE_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _endpoint(path: str) -> str:
    return urljoin(f"{_base_url()}/", path.lstrip("/"))


def _extract_error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
    return fallback


def generate_image(prompt: str, *, timeout: float | None = None) -> GeneratedMedia:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise OpenAIImageError("Image prompt cannot be empty.")

    payload = {
        "model": _env("OPENAI_IMAGE_MODEL", DEFAULT_OPENAI_IMAGE_MODEL),
        "prompt": clean_prompt,
        "n": 1,
        "size": _env("OPENAI_IMAGE_SIZE", DEFAULT_OPENAI_IMAGE_SIZE),
        "quality": _env("OPENAI_IMAGE_QUALITY", DEFAULT_OPENAI_IMAGE_QUALITY),
        "output_format": "jpeg",
    }
    response = requests.post(
        _endpoint("/v1/images/generations"),
        headers=_headers(),
        json=payload,
        timeout=timeout or _timeout(),
    )

    try:
        response_payload = response.json()
    except Exception:
        response_payload = None

    try:
        response.raise_for_status()
    except Exception as exc:
        message = _extract_error_message(response_payload, f"OpenAI image request failed: {exc}")
        raise OpenAIImageError(f"OpenAI image request failed: {message}") from exc

    data = response_payload.get("data") if isinstance(response_payload, dict) else None
    if not isinstance(data, list) or not data:
        raise OpenAIImageError("OpenAI image response did not include image data.")

    b64_json = data[0].get("b64_json") if isinstance(data[0], dict) else None
    if not b64_json:
        raise OpenAIImageError("OpenAI image response did not include b64_json.")
    try:
        image_bytes = base64.b64decode(str(b64_json), validate=True)
    except Exception as exc:
        raise OpenAIImageError("OpenAI image payload is not valid base64.") from exc
    if not image_bytes:
        raise OpenAIImageError("OpenAI generated empty image data.")

    return GeneratedMedia(
        data=image_bytes,
        media_type="image/jpeg",
        file_extension="jpeg",
        trace_id=response.headers.get("x-request-id"),
        extra_info=response_payload.get("usage") if isinstance(response_payload.get("usage"), dict) else None,
    )
