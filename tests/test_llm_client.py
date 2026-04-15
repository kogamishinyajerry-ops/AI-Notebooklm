import pytest

from core.llm.client import resolve_local_llm_config


def test_resolve_local_llm_config_rejects_public_endpoint(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "https://api.minimaxi.com/anthropic/v1/messages")

    with pytest.raises(ValueError, match="Public LLM endpoint is forbidden"):
        resolve_local_llm_config()


def test_resolve_local_llm_config_accepts_localhost(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "Qwen2.5-14B-Instruct")

    config = resolve_local_llm_config()

    assert config.base_url == "http://127.0.0.1:8001/v1"
    assert config.model == "Qwen2.5-14B-Instruct"
