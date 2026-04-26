# Retrieval Quality Baseline

This document is the canonical reference for how the COMAC NotebookLM
retrieval pipeline is evaluated against a frozen baseline, and for the
W-V43-13 mitigation of the R-2604-04 hardware-locked sentinel risk.

## Files

| Path | Purpose |
|---|---|
| `tests/retrieval_quality_baseline/queries.yaml` | 30 golden queries (20 FAA + 10 CCAR) |
| `tests/retrieval_quality_baseline/baseline.json` | Recorded MRR@5 / NDCG@5 / Recall@5 / hit_rate at the reference commit |
| `tests/retrieval_quality_baseline/evaluator.py` | Pure-Python metric primitives (no scikit-learn) |
| `tests/test_retrieval_quality_regression.py` | Live-pipeline regression test (embeddings → ChromaDB → reranker → metrics) |
| `tests/test_retrieval_metric_canonical.py` | **W-V43-13** metric-layer canonical sentinel (hardware-independent) |

## Two layers of regression detection

### Layer 1 — Live pipeline (`test_retrieval_quality_regression.py`)

Runs the real retrieval engine end-to-end (`bge-large-zh-v1.5`
embeddings, ChromaDB HNSW, `bge-reranker-base`, RRF fusion, graph
expansion). Captures regressions at the embedding, indexing, ranking,
or fusion layer. **Hardware-locked** — the same code can produce
slightly different MRR/NDCG/Recall on different Apple Silicon machines
because of floating-point ordering inside the HNSW search graph and
BLAS kernels. The current `regression_threshold_pct` is 5%, but
observed cross-machine drift has reached ~12% on a fresh
`/tmp` worktree (W-V43-10 §4.5; R-2604-04).

### Layer 2 — Metric-layer canonical (`test_retrieval_metric_canonical.py`)

Feeds the canonical `per_query_summary` from `baseline.json` directly
into the metric primitives and asserts they reproduce the recorded
aggregate metrics exactly. Pure-Python, deterministic, no model load.
Runs in milliseconds on any machine. Catches metric-formula refactors
that would otherwise hide behind the live-pipeline noise.

## R-2604-04 mitigation status (W-V43-13)

| Aspect | Status |
|---|---|
| Metric layer determinism | **Mitigated** — `test_retrieval_metric_canonical.py` enforces it |
| `baseline.json` self-consistency | **Mitigated** — `test_baseline_json_metric_self_consistency` covers it |
| Cross-machine engine layer reproducibility | **Open / deferred** — full pre-computed embedding fixture (Option B) requires mocking ChromaDB HNSW; deferred to Window 5+ |
| Threshold tuning | unchanged at 5%; the metric sentinel anchors the baseline so future threshold debates can isolate "engine drift" from "metric drift" |

The full Option B (frozen embedding/retrieval fixtures consumed by
`test_retrieval_quality_regression.py` instead of running the live
engine) was scheduled but deferred because it requires:

- Capturing per-query top-K chunk IDs at the canonical commit on a
  reference machine
- Mocking `core.retrieval.embeddings.EmbeddingManager` and the ChromaDB
  vector store with fixture-backed fakes
- A migration plan for the live test (does it stay as a long-running
  smoke, or does it move to a separate marker?)

The metric-layer sentinel landed in W-V43-13 captures the *invariant*
that survives any future engine-layer refactor: aggregate metrics
computed from the canonical per-query summary must equal the recorded
baseline metrics. That invariant is what previous Window-3 debugging
needed to distinguish "metric drift" from "engine drift" but didn't
have.

## Updating the baseline

Re-recording the baseline is a deliberate human-gated action, not an
automatic process. The procedure (preserved verbatim from V4.1-T1):

1. Run `tests/test_retrieval_quality_regression.py` with the new
   pipeline configuration on the canonical recording machine
2. Record the new aggregate metrics + per-query summary into
   `baseline.json`, bumping `baseline_commit` and `recorded_at`
3. Open a PR; require Opus Gate Review approval for any metric drop
   greater than 5% relative to the previous baseline (per the
   `update_policy` field)
4. Update this document with the rationale for the change

## Operator runbook: live pipeline failure on a fresh machine

If you check out a fresh worktree and `test_mrr_no_regression` fails:

1. Check the metric-layer sentinel:
   `python3 -m pytest tests/test_retrieval_metric_canonical.py -v`
2. If the metric sentinel **passes**: the failure is engine-layer drift
   (R-2604-04). The drift is real but tracks the chromadb/torch
   floating-point ordering of your hardware, not a code regression.
   File a sub-issue for Option B if cross-machine reproducibility
   becomes blocking.
3. If the metric sentinel **fails**: a metric-formula refactor
   regressed `evaluator.py` or someone edited `baseline.json`
   inconsistently. Treat as a hard regression and revert the offending
   change.
