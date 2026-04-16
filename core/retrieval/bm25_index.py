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

import math
import re
from collections import Counter
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


class _FallbackBM25Okapi:
    """
    Small pure-Python BM25 scorer used when ``rank_bm25`` is unavailable.

    The interface intentionally mirrors the subset we use from
    ``rank_bm25.BM25Okapi`` so tests and callers can rely on ``get_scores()``.
    """

    def __init__(self, corpus_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus_tokens = corpus_tokens
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus_tokens)
        self.doc_lens = [len(tokens) for tokens in corpus_tokens]
        self.avgdl = (
            sum(self.doc_lens) / self.corpus_size if self.corpus_size else 0.0
        )
        self.doc_freqs: List[Counter[str]] = [Counter(tokens) for tokens in corpus_tokens]
        self.term_doc_count: Counter[str] = Counter()

        for freqs in self.doc_freqs:
            for term in freqs:
                self.term_doc_count[term] += 1

    def _idf(self, term: str) -> float:
        df = self.term_doc_count.get(term, 0)
        if df == 0 or self.corpus_size == 0:
            return 0.0
        # Positive BM25-style IDF; avoids negative weights for common terms
        # while staying faithful to lexical ranking behavior.
        return math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        if not self.corpus_tokens:
            return []

        scores = [0.0] * self.corpus_size
        unique_terms = list(dict.fromkeys(query_tokens))

        for doc_idx, term_freqs in enumerate(self.doc_freqs):
            doc_len = self.doc_lens[doc_idx]
            norm = self.k1 * (
                1.0 - self.b + self.b * (doc_len / self.avgdl if self.avgdl else 0.0)
            )

            score = 0.0
            for term in unique_terms:
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf(term)
                denom = tf + norm
                if denom == 0:
                    continue
                score += idf * (tf * (self.k1 + 1.0)) / denom

            scores[doc_idx] = score

        return scores


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
            self._bm25 = _FallbackBM25Okapi(tokenized)

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
