from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.llm.vllm_client import (
    LLMConfigurationError,
    get_local_llm_config,
    probe_local_llm,
)


def test_default_vllm_config_uses_local_endpoint(monkeypatch):
    monkeypatch.delenv("VLLM_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)

    config = get_local_llm_config()

    assert config.base_url == "http://localhost:8001/v1"
    assert config.model_name == "qwen-2.5"
    assert config.is_private_network is True


def test_public_vllm_url_rejected_by_default(monkeypatch):
    monkeypatch.setenv("VLLM_URL", "https://example.com/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_local_llm_config()


def test_public_vllm_url_allowed_with_explicit_override(monkeypatch):
    monkeypatch.setenv("VLLM_URL", "https://example.com/v1")
    monkeypatch.setenv("ALLOW_REMOTE_VLLM", "1")

    config = get_local_llm_config()

    assert config.base_url == "https://example.com/v1"
    assert config.is_private_network is False


def test_probe_local_llm_calls_models_endpoint(monkeypatch):
    monkeypatch.setenv("VLLM_URL", "http://127.0.0.1:8001/v1")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"id": "qwen-2.5"},
            {"id": "glm-4"},
        ]
    }
    fake_response.raise_for_status.return_value = None

    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return fake_response

    monkeypatch.setattr("core.llm.vllm_client.requests.get", fake_get)

    result = probe_local_llm(timeout=1.5)

    assert captured == {"url": "http://127.0.0.1:8001/v1/models", "timeout": 1.5}
    assert result["reachable"] is True
    assert result["models"] == ["qwen-2.5", "glm-4"]


def test_probe_local_llm_reports_unreachable_service(monkeypatch):
    monkeypatch.setenv("VLLM_URL", "http://127.0.0.1:8001/v1")

    def fake_get(url, timeout):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("core.llm.vllm_client.requests.get", fake_get)

    result = probe_local_llm()

    assert result["reachable"] is False
    assert result["status"] == "unreachable"
    assert "connection refused" in result["error"]


def test_check_vllm_endpoint_script_returns_zero_when_reachable(monkeypatch):
    from scripts import check_vllm_endpoint  # noqa: PLC0415

    monkeypatch.setattr(
        check_vllm_endpoint,
        "probe_local_llm",
        lambda timeout: {"reachable": True, "status": "ok"},
    )

    assert check_vllm_endpoint.main() == 0


def test_check_vllm_endpoint_script_returns_two_on_misconfiguration(monkeypatch):
    from scripts import check_vllm_endpoint  # noqa: PLC0415

    def raise_config(timeout):
        raise LLMConfigurationError("bad vllm url")

    monkeypatch.setattr(check_vllm_endpoint, "probe_local_llm", raise_config)

    assert check_vllm_endpoint.main() == 2
