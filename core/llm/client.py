import os
from urllib.parse import urlparse

import requests


_DEFAULT_LOCAL_ENDPOINT = "http://localhost:8000/v1/chat/completions"


def _is_local_endpoint(endpoint: str) -> bool:
    host = urlparse(endpoint).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def call_local_llm(system_prompt: str, user_query: str) -> str:
    endpoint = os.environ.get("LOCAL_LLM_ENDPOINT", _DEFAULT_LOCAL_ENDPOINT)
    if not _is_local_endpoint(endpoint):
        raise ValueError("LOCAL_LLM_ENDPOINT must point to a local endpoint")

    try:
        response = requests.post(
            endpoint,
            json={
                "model": os.environ.get("LOCAL_LLM_MODEL", "qwen-2.5"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ],
            },
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception:
        # Parameter extraction must never break ingestion if the local model is down.
        return "[]"
