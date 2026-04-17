from __future__ import annotations

import os
from typing import List, Dict, Any

def should_use_local_files_only_for_reranker() -> bool:
    value = os.getenv("RERANKER_LOCAL_FILES_ONLY")
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("HF_HUB_OFFLINE", "").strip() == "1"
        or os.getenv("TRANSFORMERS_OFFLINE", "").strip() == "1"
    )


class CrossEncoderReranker:
    """
    Local offline-first cross-encoder reranker.

    The model is loaded lazily and prefers local-files-only mode in production
    or when offline flags are enabled. If the reranker model is unavailable,
    retrieval degrades gracefully to the incoming candidate order instead of
    breaking the request path.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        local_files_only: bool | None = None,
    ):
        self.model_name = model_name
        self.local_files_only = (
            should_use_local_files_only_for_reranker()
            if local_files_only is None
            else local_files_only
        )
        self._model = None
        self._load_error: Exception | None = None

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        """
        Score candidates with the local reranker and return the top-N results.

        If the model cannot be loaded or prediction fails, the method falls
        back to the original candidate order to preserve availability.
        """
        if not chunks or top_n <= 0:
            return []

        model = self._ensure_model()
        if model is None:
            return chunks[:top_n]

        pairs = [(query, chunk.get("text", "")) for chunk in chunks]
        try:
            scores = model.predict(pairs)
        except Exception as exc:
            self._load_error = exc
            return chunks[:top_n]

        ranked = sorted(
            enumerate(chunks),
            key=lambda item: (-float(scores[item[0]]), item[0]),
        )

        reranked: List[Dict[str, Any]] = []
        for index, chunk in ranked[:top_n]:
            item = dict(chunk)
            item["reranker_score"] = float(scores[index])
            reranked.append(item)
        return reranked

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            return None

        try:
            from sentence_transformers import CrossEncoder
        except Exception as exc:
            self._load_error = exc
            return None

        try:
            self._model = CrossEncoder(
                self.model_name,
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            self._load_error = exc
            self._model = None

        return self._model
