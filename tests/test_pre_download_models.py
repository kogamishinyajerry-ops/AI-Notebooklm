from __future__ import annotations

import importlib

import pytest


def _load_script_module():
    return importlib.import_module("scripts.pre_download_models")


def test_preload_models_uses_configured_model_names(monkeypatch):
    module = _load_script_module()
    calls = []

    def fake_sentence_transformer(model_name, local_files_only):
        calls.append(("embedding", model_name, local_files_only))
        return object()

    def fake_cross_encoder(model_name, local_files_only):
        calls.append(("reranker", model_name, local_files_only))
        return object()

    monkeypatch.setattr(module, "_load_sentence_transformer_cls", lambda: fake_sentence_transformer)
    monkeypatch.setattr(module, "_load_cross_encoder_cls", lambda: fake_cross_encoder)

    result = module.preload_models(
        embedding_model="custom-embedding",
        reranker_model="custom-reranker",
        strict=True,
    )

    assert result["errors"] == []
    assert calls == [
        ("embedding", "custom-embedding", False),
        ("reranker", "custom-reranker", False),
    ]


def test_preload_models_raises_in_strict_mode(monkeypatch):
    module = _load_script_module()

    def fake_sentence_transformer(model_name, local_files_only):
        raise RuntimeError("download failed")

    def fake_cross_encoder(model_name, local_files_only):
        return object()

    monkeypatch.setattr(module, "_load_sentence_transformer_cls", lambda: fake_sentence_transformer)
    monkeypatch.setattr(module, "_load_cross_encoder_cls", lambda: fake_cross_encoder)

    with pytest.raises(RuntimeError) as exc_info:
        module.preload_models(
            embedding_model="broken-model",
            reranker_model="working-model",
            strict=True,
        )

    assert "broken-model" in str(exc_info.value)


def test_preload_models_collects_errors_when_not_strict(monkeypatch):
    module = _load_script_module()

    def fake_sentence_transformer(model_name, local_files_only):
        raise RuntimeError("embedding missing")

    def fake_cross_encoder(model_name, local_files_only):
        raise RuntimeError("reranker missing")

    monkeypatch.setattr(module, "_load_sentence_transformer_cls", lambda: fake_sentence_transformer)
    monkeypatch.setattr(module, "_load_cross_encoder_cls", lambda: fake_cross_encoder)

    result = module.preload_models(strict=False)

    assert len(result["errors"]) == 2
