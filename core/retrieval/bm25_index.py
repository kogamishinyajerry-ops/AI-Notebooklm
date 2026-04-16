"""
core/retrieval/bm25_index.py
============================
Lightweight per-notebook BM25 index built on ``rank_bm25`` (pure Python).

The index is rebuilt in-memory from a corpus of (text, metadata) pairs.
It is NOT persisted to disk — callers rebuild it after ingestion completes.

Usage::

    idx = BM25Index()
    idx.build([("chunk text 1", meta1), ("chunk text 2", meta2)])
    results = idx.query("search terms", top_k=10)
    # returns list of {"text": str, "metadata": dict}
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional


def _tokenize(text: str) -> List[str]:
    """Simple CJK-aware tokenizer: split on whitespace + punctuation."""
    # Split Chinese characters individually, keep ASCII words intact
    tokens: List[str] = []
    for token in re.split(r"[\s\u3000\uff0c\u3002\uff1b\uff1a\uff01\uff1f\u300a\u300b\u3010\u3011]+", text):
        if not token:
            continue
        # Further split runs of CJK characters into bigrams for better recall
        cjk_buf: List[str] = []
        ascii_buf: List[str] = []
        for ch in token:
            if "\u4e00" <= ch <= "\u9fff":
                if ascii_buf:
                    tokens.append("".join(ascii_buf).lower())
                    ascii_buf = []
                cjk_buf.append(ch)
            else:
                if cjk_buf:
                    # Emit CJK bigrams
                    for i in range(len(cjk_buf)):
                        tokens.append(cjk_buf[i])
                        if i + 1 < len(cjk_buf):
                            tokens.append(cjk_buf[i] + cjk_buf[i + 1])
                    cjk_buf = []
                ascii_buf.append(ch)
        if cjk_buf:
            for i in range(len(cjk_buf)):
                tokens.append(cjk_buf[i])
                if i + 1 < len(cjk_buf):
                    tokens.append(cjk_buf[i] + cjk_buf[i + 1])
        if ascii_buf:
            tokens.append("".join(ascii_buf).lower())
    return [t for t in tokens if len(t) >= 1]


class BM25Index:
    """
    In-memory BM25 index wrapping ``rank_bm25.BM25Okapi``.

    Falls back gracefully if ``rank_bm25`` is not installed: queries return
    an empty list so the hybrid pipeline degrades to vector-only mode.
    """

    def __init__(self) -> None:
        self._corpus: List[Tuple[str, Dict[str, Any]]] = []
        self._bm25 = None  # rank_bm25.BM25Okapi instance or None

    # ------------------------------------------------------------------
    def build(self, corpus: List[Tuple[str, Dict[str, Any]]]) -> None:
        """
        Build the index from a list of (text, metadata) pairs.

        Parameters
        ----------
        corpus:
            Each element is (chunk_text, metadata_dict).
        """
        self._corpus = list(corpus)
        tokenized = [_tokenize(text) for text, _ in self._corpus]

        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            self._bm25 = BM25Okapi(tokenized)
        except ImportError:
            self._bm25 = None

    # ------------------------------------------------------------------
    def query(
        self,
        query: str,
        top_k: int = 10,
        extra_tokens: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Score all documents and return the top-k by BM25 score.

        Parameters
        ----------
        query:
            Natural language query.
        top_k:
            Maximum number of results to return.
        extra_tokens:
            Additional tokens to include (e.g., from query expansion).

        Returns
        -------
        List of dicts: ``{"text": str, "metadata": dict, "bm25_score": float}``
        """
        if self._bm25 is None or not self._corpus:
            return []

        tokens = _tokenize(query)
        if extra_tokens:
            tokens = list(set(tokens) | set(extra_tokens))

        scores = self._bm25.get_scores(tokens)

        # Sort by score descending
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in ranked[:top_k]:
            if score <= 0:
                break
            text, meta = self._corpus[idx]
            results.append({"text": text, "metadata": meta, "bm25_score": float(score)})
        return results

    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self._corpus)
