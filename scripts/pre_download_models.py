from __future__ import annotations

import os
from typing import Dict, List


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_sentence_transformer_cls():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def _load_cross_encoder_cls():
    from sentence_transformers import CrossEncoder

    return CrossEncoder


def preload_models(
    embedding_model: str | None = None,
    reranker_model: str | None = None,
    *,
    strict: bool | None = None,
) -> Dict[str, object]:
    embedding_model = embedding_model or os.getenv(
        "EMBEDDING_MODEL_NAME",
        DEFAULT_EMBEDDING_MODEL,
    )
    reranker_model = reranker_model or os.getenv(
        "RERANKER_MODEL_NAME",
        DEFAULT_RERANKER_MODEL,
    )
    strict_mode = _env_flag("MODEL_DOWNLOAD_STRICT", default=False) if strict is None else strict

    errors: List[str] = []
    sentence_transformer_cls = _load_sentence_transformer_cls()
    cross_encoder_cls = _load_cross_encoder_cls()

    print(f"Caching embedding model: {embedding_model}")
    try:
        sentence_transformer_cls(embedding_model, local_files_only=False)
        print("Embedding model successfully cached.")
    except Exception as exc:  # pragma: no cover - exercised via return path
        message = f"Embedding model '{embedding_model}' cache failed: {exc}"
        print(f"Warning: {message}")
        errors.append(message)

    print(f"Caching reranker model: {reranker_model}")
    try:
        cross_encoder_cls(reranker_model, local_files_only=False)
        print("Reranker model successfully cached.")
    except Exception as exc:  # pragma: no cover - exercised via return path
        message = f"Reranker model '{reranker_model}' cache failed: {exc}"
        print(f"Warning: {message}")
        errors.append(message)

    if errors and strict_mode:
        raise RuntimeError(" | ".join(errors))

    return {
        "embedding_model": embedding_model,
        "reranker_model": reranker_model,
        "errors": errors,
        "strict": strict_mode,
    }


def main() -> int:
    preload_models()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
