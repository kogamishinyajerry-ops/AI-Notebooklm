import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """
    Offline BGE reranker with graceful fallback.

    If the local cross-encoder model cannot be loaded, retrieval still works,
    but falls back to the incoming vector-search order instead of crashing.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

        self.model_name = os.environ.get("RERANKER_MODEL_PATH", model_name)
        self.cache_dir = os.environ.get("HF_HOME", "models")
        self.max_length = int(os.environ.get("RERANKER_MAX_LENGTH", "512"))
        self._model = None
        self._load_attempted = False

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        if top_n <= 0:
            return []

        model = self._get_model()
        if model is None:
            return chunks[:top_n]

        pairs = [[query, chunk.get("text", "")] for chunk in chunks]
        try:
            scores = model.predict(
                pairs,
                batch_size=min(16, max(1, len(pairs))),
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except Exception as exc:
            logger.warning("[Reranker] 本地重排序推理失败，退回向量召回顺序: %s", exc)
            return chunks[:top_n]

        ranked = []
        for chunk, score in zip(chunks, scores.tolist() if hasattr(scores, "tolist") else scores):
            score_value = float(score)
            ranked.append({
                **chunk,
                "metadata": {
                    **chunk.get("metadata", {}),
                    "_rerank_score": score_value,
                },
            })

        ranked.sort(key=lambda item: item["metadata"].get("_rerank_score", float("-inf")), reverse=True)
        return ranked[:top_n]

    def _get_model(self) -> Optional[Any]:
        if self._load_attempted:
            return self._model

        self._load_attempted = True
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                max_length=self.max_length,
                local_files_only=True,
                tokenizer_args={"cache_dir": self.cache_dir},
                automodel_args={"cache_dir": self.cache_dir},
            )
            logger.info("[Reranker] 本地模型已加载: %s", self.model_name)
        except Exception as exc:
            logger.warning("[Reranker] 本地模型不可用，退回向量召回顺序: %s", exc)
            self._model = None

        return self._model
