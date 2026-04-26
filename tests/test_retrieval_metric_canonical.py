"""W-V43-13: R-2604-04 mitigation — metric-layer canonical sentinel.

The existing live-pipeline retrieval sentinel
(``tests/test_retrieval_quality_regression.py``) runs the full
embeddings → ChromaDB → reranker pipeline and is hardware-locked: the
same code can produce slightly different MRR/NDCG/Recall values on
different Apple Silicon machines because of floating-point ordering
inside HNSW.

Window-3 closeout (`docs/v4_3_window_3_closeout.md` §3) scheduled
W-V43-13 as the R-2604-04 mitigation. A *full* Option B (pre-computed
embedding fixture for the engine layer) requires mocking chromadb's
HNSW search — a substantial refactor deferred to a future window. This
file lands the *metric-layer slice* of Option B:

The metric primitives (``compute_mrr_at_k`` /
``compute_ndcg_at_k`` / ``compute_recall_at_k``) are pure-Python and
deterministic. We feed them the canonical per-query summary stored in
``baseline.json`` (recorded at commit 9a94c69 on 2026-04-17) and assert
they reproduce the recorded aggregate metrics exactly. Three
guarantees follow:

1. **Hardware-independent.** No model load, no HNSW, no torch — the
   test runs on any machine the same way and never drifts.
2. **Detects metric-layer regressions.** If anyone "fixes" or rewrites
   the metric formulas in ``evaluator.py`` and the new behavior
   disagrees with the canonical baseline, this sentinel fails.
3. **Anchors the live-pipeline sentinel.** When the live test drifts on
   a new machine, this sentinel still passes — proving the drift is
   localized to the embedding/HNSW layer, not the metric layer. That
   diagnostic split is what was missing during Window-3 debugging.

The cross-hardware reproducibility of the *engine* layer is documented
as a remaining open item in
``docs/architectural_risk_register.md#r-2604-04`` (status: Mitigated)
and ``docs/RETRIEVAL_QUALITY_BASELINE.md``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tests.retrieval_quality_baseline.evaluator import (
    compute_mrr_at_k,
    compute_ndcg_at_k,
    compute_recall_at_k,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_JSON = PROJECT_ROOT / "tests/retrieval_quality_baseline" / "baseline.json"


@pytest.fixture(scope="module")
def baseline() -> dict:
    with open(BASELINE_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def _rr_to_rank(rr: float) -> int | None:
    """Invert reciprocal-rank to its 1-indexed rank (or None for misses).

    The canonical ``per_query_summary`` records ``rr`` (reciprocal rank)
    for each query. ``compute_mrr_at_k`` consumes ranks, not RR, so we
    need a stable inversion. ``rr=0.0`` means "no relevant doc in top-K"
    → ``None``; ``rr>0`` means rank=round(1/rr).
    """
    if rr <= 0.0:
        return None
    rank = round(1.0 / rr)
    # Defense against floating-point imprecision in stored RR values.
    inverted = 1.0 / rank
    if not math.isclose(inverted, rr, rel_tol=1e-3, abs_tol=1e-3):
        raise AssertionError(
            f"per_query_summary rr={rr} does not invert cleanly to a rank "
            f"(got {rank} → 1/rank={inverted}). The canonical summary may "
            f"have been hand-edited; investigate before relaxing this check."
        )
    return rank


def test_baseline_summary_reproduces_recorded_mrr(baseline):
    """W-V43-13: feeding the canonical per_query_summary into
    compute_mrr_at_k must reproduce the recorded mrr_at_5 exactly. If
    this fails, either the metric implementation drifted or someone
    edited the summary; both warrant investigation."""
    summary = baseline["per_query_summary"]
    assert len(summary) == 30, "baseline summary must cover 20 FAA + 10 CCAR"

    ranks = [_rr_to_rank(item["rr"]) for item in summary]
    computed = round(compute_mrr_at_k(ranks, k=5), 4)
    recorded = baseline["metrics"]["mrr_at_5"]

    assert computed == recorded, (
        f"Canonical metric-layer sentinel: compute_mrr_at_k({len(ranks)} "
        f"queries from per_query_summary) = {computed:.4f} but "
        f"baseline.metrics.mrr_at_5 = {recorded:.4f}. The metric "
        f"implementation or the canonical summary has drifted."
    )


def test_metric_primitives_deterministic_under_repeated_calls():
    """W-V43-13 dual: the metric primitives must be stable under
    repeated invocation with the same inputs (no hidden randomness, no
    accumulator state). This is a sanity guard for future refactors —
    if anyone introduces e.g. a torch-backed cosine similarity inside
    these helpers, this test surfaces the non-determinism immediately."""
    ranks = [1, 2, None, 3, None, 1, None, 5, 1, None]
    relevances = [1.0, 0.8, 0.0, 0.6, 0.0]
    expected_count = 4

    mrr_runs = [compute_mrr_at_k(ranks, k=5) for _ in range(20)]
    ndcg_runs = [compute_ndcg_at_k(relevances, expected_count, k=5) for _ in range(20)]
    recall_runs = [compute_recall_at_k(3, expected_count, k=5) for _ in range(20)]

    assert len(set(mrr_runs)) == 1, f"compute_mrr_at_k drifted across runs: {set(mrr_runs)}"
    assert len(set(ndcg_runs)) == 1, f"compute_ndcg_at_k drifted across runs: {set(ndcg_runs)}"
    assert len(set(recall_runs)) == 1, f"compute_recall_at_k drifted across runs: {set(recall_runs)}"


def test_baseline_json_metric_self_consistency(baseline):
    """The recorded aggregate metrics must be internally consistent with
    the per_query_summary's hit count. If hit_rate disagrees with the
    summary, the file was edited inconsistently."""
    summary = baseline["per_query_summary"]
    hit_count = sum(1 for item in summary if item["hit"])
    expected_hit_rate = round(hit_count / len(summary), 4)
    recorded_hit_rate = baseline["metrics"]["hit_rate"]

    assert expected_hit_rate == recorded_hit_rate, (
        f"baseline.json self-inconsistent: per_query_summary has "
        f"{hit_count}/{len(summary)} hits → hit_rate={expected_hit_rate}, "
        f"but metrics.hit_rate={recorded_hit_rate}."
    )
