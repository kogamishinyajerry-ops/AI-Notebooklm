"""
V4.1-T1: Retrieval Quality Baseline Evaluators
==============================================
Pure-Python implementations of MRR@K, NDCG@K, and Recall@K.
No external dependencies (no scikit-learn).

The baseline runner (`run_baseline`) orchestrates:
  1. Loading the golden queries from queries.yaml
  2. Running the retriever for each query
  3. Computing per-query hit/keyword/page match
  4. Aggregating MRR@5 / NDCG@5 / Recall@5 across the full query set
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Sequence

import yaml


# ---------------------------------------------------------------------------
# Metric primitives
# ---------------------------------------------------------------------------


def compute_mrr_at_k(
    predicted_ranks: Sequence[int | None],
    k: int = 5,
) -> float:
    """
    Mean Reciprocal Rank @ K.

    Parameters
    ----------
    predicted_ranks:
        Per-query rank of the first relevant result (1-indexed),
        or None if no relevant result within top-K.
    k:
        Cutoff rank (default 5).

    Returns
    -------
    MRR@K as a float in [0.0, 1.0].
    """
    if not predicted_ranks:
        return 0.0
    total = 0.0
    count = 0
    for rank in predicted_ranks:
        if rank is not None and rank <= k:
            total += 1.0 / rank
            count += 1
        else:
            count += 1  # count even non-hits (RR=0)
    return total / count if count else 0.0


def _dcg_at_k(relevances: Sequence[float], k: int) -> float:
    """Discounted Cumulative Gain at K with standard log2(i+1) discount."""
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        dcg += rel / math.log2(i + 2)  # i+2 because log2(1)=0
    return dcg


def _ideal_relevances(expected_count: int, k: int) -> List[float]:
    """Ideal relevance vector: all 1.0 for up to expected_count, then 0."""
    return [1.0] * min(expected_count, k)


def compute_ndcg_at_k(
    predicted_relevances: Sequence[float],
    expected_count: int,
    k: int = 5,
) -> float:
    """
    Normalized Discounted Cumulative Gain @ K.

    Parameters
    ----------
    predicted_relevances:
        Per-query relevance grades in top-K order.
        Binary (1.0 / 0.0) matching the hit signal.
    expected_count:
        Number of relevant documents for this query (from expected_pages length).
    k:
        Cutoff rank (default 5).

    Returns
    -------
    NDCG@K as a float in [0.0, 1.0].
    """
    if not predicted_relevances:
        return 0.0
    actual_dcg = _dcg_at_k(list(predicted_relevances), k)
    ideal_rel = _ideal_relevances(expected_count, k)
    ideal_dcg = _dcg_at_k(ideal_rel, k)
    if ideal_dcg == 0.0:
        # No expected relevant docs — NDCG is undefined but we treat
        # no hits as 0 (not 1) to avoid inflating the average.
        return 0.0
    return actual_dcg / ideal_dcg


def compute_recall_at_k(
    hit_count: int,
    expected_count: int,
    k: int = 5,
) -> float:
    """
    Recall @ K — fraction of expected relevant docs retrieved in top-K.

    Parameters
    ----------
    hit_count:
        Number of expected documents found within top-K.
    expected_count:
        Total number of expected relevant documents for this query.
    k:
        Cutoff rank (default 5).

    Returns
    -------
    Recall@K as a float in [0.0, 1.0].
    """
    if expected_count <= 0:
        return 1.0 if hit_count == 0 else 0.0
    return min(hit_count, k) / expected_count


# ---------------------------------------------------------------------------
# Query / case loading
# ---------------------------------------------------------------------------


class GoldenCase:
    """Plain dataclass equivalent for a golden query."""

    __slots__ = (
        "id",
        "question",
        "expected_pages",
        "keywords",
        "notebook_id",
        "corpus",
        "note",
    )

    def __init__(
        self,
        id: str,
        question: str,
        expected_pages: List[int],
        keywords: List[str],
        notebook_id: str,
        corpus: str,
        note: str | None = None,
    ) -> None:
        self.id = id
        self.question = question
        self.expected_pages = expected_pages
        self.keywords = keywords
        self.notebook_id = notebook_id
        self.corpus = corpus
        self.note = note

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoldenCase":
        return cls(
            id=str(data["id"]),
            question=str(data["question"]),
            expected_pages=[int(p) for p in data.get("expected_pages", [])],
            keywords=[str(k) for k in data.get("keywords", [])],
            notebook_id=str(data.get("notebook_id", "")),
            corpus=str(data.get("corpus", "")),
            note=data.get("note"),
        )


def load_queries_yaml(path: str | Path) -> Dict[str, List[GoldenCase]]:
    """
    Load golden queries from a queries.yaml file.

    Returns
    -------
    {"faa": [...], "ccar": [...]} lists of GoldenCase objects.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    faa_cases = [GoldenCase.from_dict(q) for q in data.get("faa_queries", [])]
    ccar_cases = [GoldenCase.from_dict(q) for q in data.get("ccar_queries", [])]
    return {"faa": faa_cases, "ccar": ccar_cases}


# ---------------------------------------------------------------------------
# Hit detection
# ---------------------------------------------------------------------------


def _result_page(result: Dict[str, Any]) -> int | None:
    meta = result.get("metadata") or {}
    page = meta.get("page")
    try:
        return int(page) if page is not None else None
    except (TypeError, ValueError):
        return None


def _is_hit(result: Dict[str, Any], case: GoldenCase) -> bool:
    """
    Return True if a single result chunk matches by keyword.

    Page matching against expected_pages is disabled — the synthetic corpus
    uses arbitrary page numbers that don't correspond to the real PDF.
    Keyword-only matching is used for all hit detection in CI.
    """
    text = str(result.get("text", "")).lower()
    for kw in case.keywords:
        if kw.lower() in text:
            return True
    return False


def _count_hits_in_top_k(
    retrieved: List[Dict[str, Any]],
    case: GoldenCase,
    k: int,
) -> tuple[int, List[float]]:
    """
    Count keyword-matched results in top-K and build binary relevance vector for NDCG.

    Note: page-based hit counting is replaced by keyword-only matching because
    the synthetic corpus uses arbitrary page numbers. Each query has exactly one
    relevant synthetic chunk; hit_count reflects whether that chunk appeared in top-K.

    Returns
    -------
    (hit_count, relevance_vector) where relevance_vector has len <= k.
    """
    relevance: List[float] = []
    hit_texts: set = set()
    for result in retrieved[:k]:
        if _is_hit(result, case):
            relevance.append(1.0)
            hit_texts.add(result.get("text", "")[:200])  # dedupe by text prefix
        else:
            relevance.append(0.0)
    return len(hit_texts), relevance


# ---------------------------------------------------------------------------
# Per-query evaluation
# ---------------------------------------------------------------------------


class QueryEvalResult:
    """Lightweight result container for a single golden query evaluation."""

    __slots__ = (
        "query_id",
        "question",
        "hit",
        "first_hit_rank",
        "reciprocal_rank",
        "hit_count",
        "expected_count",
        "relevance_vector",
        "top_k",
    )

    def __init__(
        self,
        query_id: str,
        question: str,
        hit: bool,
        first_hit_rank: int | None,
        reciprocal_rank: float,
        hit_count: int,
        expected_count: int,
        relevance_vector: List[float],
        top_k: int,
    ) -> None:
        self.query_id = query_id
        self.question = question
        self.hit = hit
        self.first_hit_rank = first_hit_rank
        self.reciprocal_rank = reciprocal_rank
        self.hit_count = hit_count
        self.expected_count = expected_count
        self.relevance_vector = relevance_vector
        self.top_k = top_k

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "question": self.question,
            "hit": self.hit,
            "first_hit_rank": self.first_hit_rank,
            "reciprocal_rank": self.reciprocal_rank,
            "hit_count": self.hit_count,
            "expected_count": self.expected_count,
            "relevance_vector": self.relevance_vector,
            "top_k": self.top_k,
        }


def evaluate_single_query(
    case: GoldenCase,
    retrieved: List[Dict[str, Any]],
    top_k: int = 5,
) -> QueryEvalResult:
    """
    Evaluate a single golden query against retrieved results.

    Parameters
    ----------
    case:
        GoldenCase with expected_pages and keywords.
    retrieved:
        List of dicts as returned by RetrieverEngine.retrieve()
        (each dict has "text" and "metadata" keys).
    top_k:
        Number of top results to consider.

    Returns
    -------
    QueryEvalResult with per-query metrics.
    """
    hit_count, relevance_vector = _count_hits_in_top_k(retrieved, case, top_k)

    # Find first hit rank
    first_hit_rank: int | None = None
    for i, result in enumerate(retrieved[:top_k]):
        if _is_hit(result, case):
            first_hit_rank = i + 1  # 1-indexed
            break

    reciprocal_rank = (1.0 / first_hit_rank) if first_hit_rank else 0.0

    return QueryEvalResult(
        query_id=case.id,
        question=case.question,
        hit=hit_count > 0,
        first_hit_rank=first_hit_rank,
        reciprocal_rank=reciprocal_rank,
        hit_count=hit_count,
        expected_count=len(case.expected_pages),
        relevance_vector=relevance_vector,
        top_k=top_k,
    )


# ---------------------------------------------------------------------------
# Baseline runner
# ---------------------------------------------------------------------------


def run_baseline(
    queries_yaml_path: str | Path,
    retriever: Any,
    top_k: int = 5,
    notebook_id: str = "__eval__",
) -> Dict[str, Any]:
    """
    Run the full retrieval quality baseline.

    Parameters
    ----------
    queries_yaml_path:
        Path to queries.yaml (created by V4.1-T1).
    retriever:
        A RetrieverEngine instance (or mock with `.retrieve()` method).
    top_k:
        K for MRR@K, NDCG@K, Recall@K (default 5).
    notebook_id:
        Passed to retriever.retrieve() for graph expansion scoping.

    Returns
    -------
    Dict with:
      - metrics: {mrr_at_k, ndcg_at_k, recall_at_k, total_queries, hit_rate}
      - per_query: [QueryEvalResult.to_dict(), ...]
      - config: {top_k, queries_yaml, notebook_id}
    """
    groups = load_queries_yaml(queries_yaml_path)
    all_cases: List[GoldenCase] = groups["faa"] + groups["ccar"]

    per_query: List[QueryEvalResult] = []

    for case in all_cases:
        try:
            retrieved = retriever.retrieve(
                case.question,
                top_k=top_k,
                final_k=top_k,
                notebook_id=notebook_id,
                expand_graph=True,
            )
        except TypeError:
            # Fallback for retriever.signature differences
            try:
                retrieved = retriever.retrieve(
                    case.question,
                    top_k=top_k,
                    final_k=top_k,
                    notebook_id=notebook_id,
                )
            except TypeError:
                retrieved = retriever.retrieve(
                    case.question,
                    top_k=top_k,
                    final_k=top_k,
                )

        result = evaluate_single_query(case, retrieved, top_k=top_k)
        per_query.append(result)

    # Aggregate
    total = len(per_query)
    hit_rate = sum(1 for r in per_query if r.hit) / total if total else 0.0
    mrr = compute_mrr_at_k([r.first_hit_rank for r in per_query], k=top_k)
    ndcg = sum(
        compute_ndcg_at_k(r.relevance_vector, r.expected_count, k=top_k)
        for r in per_query
    ) / total if total else 0.0
    recall = sum(
        compute_recall_at_k(r.hit_count, r.expected_count, k=top_k)
        for r in per_query
    ) / total if total else 0.0

    return {
        "metrics": {
            "mrr_at_k": round(mrr, 4),
            "ndcg_at_k": round(ndcg, 4),
            "recall_at_k": round(recall, 4),
            "hit_rate": round(hit_rate, 4),
            "total_queries": total,
            "k": top_k,
        },
        "per_query": [r.to_dict() for r in per_query],
        "config": {
            "top_k": top_k,
            "queries_yaml": str(queries_yaml_path),
            "notebook_id": notebook_id,
        },
    }
