from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urljoin

import requests

from core.llm.media_types import GeneratedMedia


DEFAULT_MINIMAX_MEDIA_BASE_URL = "https://api.minimaxi.com"
DEFAULT_MINIMAX_TTS_MODEL = "speech-2.8-hd"
DEFAULT_MINIMAX_TTS_VOICE_ID = "Chinese (Mandarin)_Reliable_Executive"
DEFAULT_MINIMAX_IMAGE_MODEL = "image-01"
DEFAULT_MINIMAX_IMAGE_ASPECT_RATIO = "16:9"
DEFAULT_MINIMAX_MEDIA_TIMEOUT = 90.0
MINIMAX_MEDIA_API_KEY_ENV = "MINIMAX_MEDIA_API_KEY"
MINIMAX_TEXT_API_KEY_ENV = "MINIMAX_API_KEY"


class MiniMaxMediaError(RuntimeError):
    """Raised when MiniMax media generation cannot produce a usable asset."""


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _timeout() -> float:
    value = os.getenv("MINIMAX_MEDIA_TIMEOUT", "").strip()
    if not value:
        return DEFAULT_MINIMAX_MEDIA_TIMEOUT
    try:
        return float(value)
    except ValueError as exc:
        raise MiniMaxMediaError("MINIMAX_MEDIA_TIMEOUT must be a number.") from exc


def _api_key() -> str:
    api_key = (
        os.getenv(MINIMAX_MEDIA_API_KEY_ENV, "").strip()
        or os.getenv(MINIMAX_TEXT_API_KEY_ENV, "").strip()
    )
    if not api_key:
        raise MiniMaxMediaError(
            "MINIMAX_MEDIA_API_KEY or MINIMAX_API_KEY is required for MiniMax media generation."
        )
    return api_key


def _base_url() -> str:
    return _env("MINIMAX_MEDIA_BASE_URL", DEFAULT_MINIMAX_MEDIA_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _endpoint(path: str) -> str:
    return urljoin(f"{_base_url()}/", path.lstrip("/"))


def _raise_minimax_error(payload: dict[str, Any], fallback: str) -> None:
    base_resp = payload.get("base_resp")
    if not isinstance(base_resp, dict):
        return
    status_code = base_resp.get("status_code")
    if status_code in (0, "0", None):
        return
    status_msg = base_resp.get("status_msg") or fallback
    raise MiniMaxMediaError(f"{fallback}: {status_msg}")


def generate_tts_audio(text: str, *, timeout: float | None = None) -> GeneratedMedia:
    clean_text = text.strip()
    if not clean_text:
        raise MiniMaxMediaError("TTS text cannot be empty.")

    payload = {
        "model": _env("MINIMAX_TTS_MODEL", DEFAULT_MINIMAX_TTS_MODEL),
        "text": clean_text[:9900],
        "stream": False,
        "language_boost": "Chinese",
        "output_format": "hex",
        "voice_setting": {
            "voice_id": _env("MINIMAX_TTS_VOICE_ID", DEFAULT_MINIMAX_TTS_VOICE_ID),
            "speed": 1,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    response = requests.post(
        _endpoint("/v1/t2a_v2"),
        headers=_headers(),
        json=payload,
        timeout=timeout or _timeout(),
    )
    try:
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        body = (getattr(response, "text", "") or "").strip()
        if len(body) > 500:
            body = f"{body[:500]}..."
        suffix = f"; response_body={body}" if body else ""
        raise MiniMaxMediaError(f"MiniMax TTS request failed: {exc}{suffix}") from exc

    _raise_minimax_error(payload, "MiniMax TTS generation failed")
    audio_hex = (payload.get("data") or {}).get("audio")
    if not audio_hex:
        raise MiniMaxMediaError("MiniMax TTS response did not include audio data.")
    try:
        audio_bytes = bytes.fromhex(str(audio_hex))
    except ValueError as exc:
        raise MiniMaxMediaError("MiniMax TTS audio payload is not valid hex.") from exc
    if not audio_bytes:
        raise MiniMaxMediaError("MiniMax TTS generated empty audio.")

    return GeneratedMedia(
        data=audio_bytes,
        media_type="audio/mpeg",
        file_extension="mp3",
        trace_id=payload.get("trace_id"),
        extra_info=payload.get("extra_info") if isinstance(payload.get("extra_info"), dict) else None,
    )


def generate_image(prompt: str, *, timeout: float | None = None) -> GeneratedMedia:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise MiniMaxMediaError("Image prompt cannot be empty.")

    payload = {
        "model": _env("MINIMAX_IMAGE_MODEL", DEFAULT_MINIMAX_IMAGE_MODEL),
        "prompt": clean_prompt,
        "aspect_ratio": _env("MINIMAX_IMAGE_ASPECT_RATIO", DEFAULT_MINIMAX_IMAGE_ASPECT_RATIO),
        "response_format": "base64",
    }
    response = requests.post(
        _endpoint("/v1/image_generation"),
        headers=_headers(),
        json=payload,
        timeout=timeout or _timeout(),
    )
    try:
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        body = (getattr(response, "text", "") or "").strip()
        if len(body) > 500:
            body = f"{body[:500]}..."
        suffix = f"; response_body={body}" if body else ""
        raise MiniMaxMediaError(f"MiniMax image request failed: {exc}{suffix}") from exc

    _raise_minimax_error(payload, "MiniMax image generation failed")
    images = (payload.get("data") or {}).get("image_base64")
    if not isinstance(images, list) or not images:
        raise MiniMaxMediaError("MiniMax image response did not include image_base64 data.")
    try:
        image_bytes = base64.b64decode(str(images[0]), validate=True)
    except Exception as exc:
        raise MiniMaxMediaError("MiniMax image payload is not valid base64.") from exc
    if not image_bytes:
        raise MiniMaxMediaError("MiniMax generated empty image data.")

    return GeneratedMedia(
        data=image_bytes,
        media_type="image/jpeg",
        file_extension="jpeg",
        trace_id=payload.get("trace_id"),
        extra_info=payload.get("extra_info") if isinstance(payload.get("extra_info"), dict) else None,
    )
