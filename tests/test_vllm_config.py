from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.llm.vllm_client import (
    LLMConfigurationError,
    get_llm_config,
    get_local_llm_config,
    invoke_llm,
    probe_local_llm,
)


def test_default_vllm_config_uses_local_endpoint(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_URL", raising=False)
    monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)

    config = get_local_llm_config()

    assert config.provider == "local"
    assert config.base_url == "http://localhost:8001/v1"
    assert config.model_name == "qwen-2.5"
    assert config.is_private_network is True
    assert config.is_loopback_host is True


def test_public_vllm_url_rejected_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "https://example.com/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_local_llm_config()


def test_public_vllm_url_allowed_with_explicit_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "https://example.com/v1")
    monkeypatch.setenv("ALLOW_REMOTE_VLLM", "1")

    config = get_local_llm_config()

    assert config.base_url == "https://example.com/v1"
    assert config.is_private_network is False
    assert config.is_loopback_host is False


def test_private_lan_url_rejected_without_explicit_override(monkeypatch):
    """W-V43-11.5: private-LAN endpoints now require ALLOW_REMOTE_VLLM=1.

    R-2604-03 mitigation: tightening default to loopback-only for the C1
    air-gap default lane. Private-LAN was implicitly allowed prior to this
    change.
    """
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://192.168.1.10:8001/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_local_llm_config()


def test_private_lan_url_allowed_with_explicit_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://192.168.1.10:8001/v1")
    monkeypatch.setenv("ALLOW_REMOTE_VLLM", "1")

    config = get_local_llm_config()

    assert config.base_url == "http://192.168.1.10:8001/v1"
    assert config.is_private_network is True
    assert config.is_loopback_host is False


def test_loopback_127_url_allowed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    config = get_local_llm_config()

    assert config.is_loopback_host is True


def test_host_docker_internal_no_longer_trusted_as_loopback(monkeypatch):
    """W-V43-11.5 Codex review: `host.docker.internal` is name-based trust.

    Docker Desktop maps it to the host machine's non-loopback IP, and
    `extra_hosts` / DNS overrides can remap it further. As of this PR it
    is no longer treated as loopback — Docker deployments must set
    ALLOW_REMOTE_VLLM=1 explicitly.
    """
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://host.docker.internal:8001/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_local_llm_config()


def test_host_docker_internal_allowed_with_explicit_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://host.docker.internal:8001/v1")
    monkeypatch.setenv("ALLOW_REMOTE_VLLM", "1")

    config = get_local_llm_config()

    assert config.is_loopback_host is False
    assert config.is_private_network is True  # still in _ALLOWED_LOCAL_HOSTS


def test_dot_local_suffix_rejected_without_explicit_override(monkeypatch):
    """W-V43-11.5: .local mDNS suffixes are private-LAN, not loopback."""
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://my-llm-box.local:8001/v1")
    monkeypatch.delenv("ALLOW_REMOTE_VLLM", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_local_llm_config()


def test_minimax_config_uses_external_validation_lane(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "secret-token")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    monkeypatch.delenv("MINIMAX_MODEL", raising=False)

    config = get_llm_config()

    assert config.provider == "minimax"
    assert config.base_url == "https://api.minimax.io/anthropic"
    assert config.model_name == "MiniMax-M2.7-highspeed"
    assert config.is_external_validation is True
    assert config.is_private_network is False


def test_minimax_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    with pytest.raises(LLMConfigurationError):
        get_llm_config()


def test_probe_local_llm_calls_models_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
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

    def fake_get(url, timeout, **kwargs):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = kwargs.get("headers")
        return fake_response

    monkeypatch.setattr("core.llm.vllm_client.requests.get", fake_get)

    result = probe_local_llm(timeout=1.5)

    assert captured == {
        "url": "http://127.0.0.1:8001/v1/models",
        "timeout": 1.5,
        "headers": None,
    }
    assert result["provider"] == "local"
    assert result["available"] is True
    assert result["reachable"] is True
    assert result["models"] == ["qwen-2.5", "glm-4"]


def test_probe_local_llm_reports_unreachable_service(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://127.0.0.1:8001/v1")

    def fake_get(url, timeout, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("core.llm.vllm_client.requests.get", fake_get)

    result = probe_local_llm()

    assert result["provider"] == "local"
    assert result["available"] is False
    assert result["reachable"] is False
    assert result["status"] == "unreachable"
    assert "connection refused" in result["error"]


def test_probe_local_llm_detects_mismatched_service(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("VLLM_URL", "http://127.0.0.1:8001/v1")

    class _Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"{self.status_code} error")

        def json(self):
            return self._payload

    def fake_get(url, timeout, **kwargs):
        if url.endswith("/v1/models"):
            return _Response(404, {"detail": "Not Found"})
        if url.endswith("/health"):
            return _Response(200, {"status": "healthy", "service": "gateway"})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("core.llm.vllm_client.requests.get", fake_get)

    result = probe_local_llm()

    assert result["provider"] == "local"
    assert result["reachable"] is False
    assert result["status"] == "mismatched_service"
    assert result["health_payload"] == {"status": "healthy", "service": "gateway"}


def test_probe_minimax_uses_anthropic_messages_probe(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "msg-test",
        "content": [{"type": "text", "text": "ok"}],
    }
    fake_response.raise_for_status.return_value = None

    captured = {}

    def fake_post(url, timeout, **kwargs):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return fake_response

    monkeypatch.setattr("core.llm.vllm_client.requests.post", fake_post)

    result = probe_local_llm(timeout=2.5)

    assert captured["url"] == "https://api.minimax.io/anthropic/v1/messages"
    assert captured["timeout"] == 2.5
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": "test-minimax-key",
    }
    assert captured["json"] == {
        "model": "MiniMax-M2.7",
        "max_tokens": 4,
        "system": "You are a health-check assistant.",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Reply with ok."}],
            }
        ],
    }
    assert result["provider"] == "minimax"
    assert result["is_external_validation"] is True
    assert result["probe_method"] == "POST"
    assert result["response_id"] == "msg-test"


def test_invoke_minimax_extracts_text_from_anthropic_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "msg-test",
        "content": [
            {"type": "thinking", "thinking": "internal reasoning"},
            {"type": "text", "text": "final answer"},
        ],
    }
    fake_response.raise_for_status.return_value = None

    captured = {}

    def fake_post(url, timeout, **kwargs):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return fake_response

    monkeypatch.setattr("core.llm.vllm_client.requests.post", fake_post)

    result = invoke_llm("system prompt", "user question", timeout=12)

    assert result == "final answer"
    assert captured["url"] == "https://api.minimax.io/anthropic/v1/messages"
    assert captured["timeout"] == 12
    assert captured["headers"]["x-api-key"] == "test-minimax-key"
    assert captured["json"]["system"] == "system prompt"
    assert captured["json"]["messages"][0]["content"][0]["text"] == "user question"


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
