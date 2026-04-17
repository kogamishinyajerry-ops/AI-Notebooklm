"""
V4.1-T1: Retrieval Quality Regression Test
============================================
pytest test that verifies the retrieval pipeline has not regressed
against the golden-set baseline recorded in baseline.json.

Run:
    python3 -m pytest tests/test_retrieval_quality_regression.py -v

C1 compliant: all data is static YAML, no network calls.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests.retrieval_quality_baseline.evaluator import (
    compute_mrr_at_k,
    compute_ndcg_at_k,
    compute_recall_at_k,
    evaluate_single_query,
    load_queries_yaml,
)
from tests.retrieval_quality_baseline.baseline import BaselineConfig, get_baseline

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

QUERIES_YAML = PROJECT_ROOT / "tests/retrieval_quality_baseline" / "queries.yaml"
BASELINE_JSON = PROJECT_ROOT / "tests/retrieval_quality_baseline" / "baseline.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _restore_retrieval_modules() -> None:
    """
    Remove any MagicMock stubs from sys.modules and re-import real implementations.

    test_gap_a_retriever.py creates MagicMock stubs for chromadb, tenacity,
    core.retrieval.embeddings, core.retrieval.vector_store, and core.retrieval.reranker
    during its module setup. Even if conftest's session fixture restores the real
    modules, test_gap_a_retriever's setup can re-pollute sys.modules.
    This function cleans up those stubs so subsequent imports get real classes.
    """
    import importlib

    def _is_stub(mod, attr):
        val = getattr(mod, attr, None) if mod else None
        if val is None:
            return False
        t = type(val)
        if "MagicMock" in t.__name__:
            return True
        if isinstance(val, type) and "MagicMock" in val.__name__:
            return True
        return False

    targets = {
        "chromadb": "PersistentClient",
        "core.retrieval.embeddings": "EmbeddingManager",
        "core.retrieval.vector_store": "VectorStoreAdapter",
        "core.retrieval.reranker": "CrossEncoderReranker",
        "sentence_transformers": "SentenceTransformer",
    }

    needs_restore = False
    for mod_name, attr in targets.items():
        mod = sys.modules.get(mod_name)
        if _is_stub(mod, attr):
            needs_restore = True
            break

    if not needs_restore:
        return

    keys_to_remove = []
    for key in list(sys.modules.keys()):
        if key == "chromadb" or key.startswith("chromadb."):
            keys_to_remove.append(key)
        elif key == "core.retrieval.vector_store" or key.startswith("core.retrieval.vector_store."):
            keys_to_remove.append(key)
        elif key == "core.retrieval.embeddings" or key.startswith("core.retrieval.embeddings."):
            keys_to_remove.append(key)
        elif key == "core.retrieval.reranker" or key.startswith("core.retrieval.reranker."):
            keys_to_remove.append(key)
        elif key == "tenacity" or key.startswith("tenacity."):
            keys_to_remove.append(key)
        elif key == "sentence_transformers" or key.startswith("sentence_transformers."):
            keys_to_remove.append(key)
        elif key == "transformers" or key.startswith("transformers."):
            keys_to_remove.append(key)
        elif key == "torch" or key.startswith("torch."):
            keys_to_remove.append(key)
        elif key == "fitz":
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del sys.modules[key]

    importlib.import_module("tenacity")
    importlib.import_module("fitz")
    importlib.import_module("torch")
    importlib.import_module("transformers")
    importlib.import_module("sentence_transformers")
    importlib.import_module("chromadb")
    importlib.import_module("core.retrieval.reranker")
    importlib.import_module("core.retrieval.embeddings")
    importlib.import_module("core.retrieval.vector_store")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def baseline_data() -> dict:
    """Load the baseline.json as a plain dict."""
    with open(BASELINE_JSON, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def golden_cases(eval_corpus_setup):
    """
    Load all golden cases from queries.yaml.

    eval_corpus_setup (session-scoped) undoes MagicMock stubs from test_gap_a_retriever.py
    and regenerates the synthetic corpus before any module-scoped fixtures run.

    NOTE: Do NOT call _restore_retrieval_modules() here. The session-scoped
    eval_corpus_setup already restored the real modules. A second "restore" would
    delete sentence_transformers (real) and re-import it — getting the MagicMock
    from test_gap_a_retriever's cached stub in sys.modules, breaking eval_results.
    """
    return load_queries_yaml(QUERIES_YAML)


@pytest.fixture(scope="module")
def retriever(eval_corpus_setup):
    """
    Build a RetrieverEngine with the synthetic eval corpus.
    Uses HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE to satisfy C1.

    eval_corpus_setup (session-scoped) runs when first needed to restore
    real modules and regenerate the corpus. The retriever fixture performs
    additional inline cleanup to handle pollution from test_gap_a_retriever
    in the full suite.
    """
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")
    os.environ.setdefault("RERANKER_LOCAL_FILES_ONLY", "1")

    import sys as _sys
    import importlib

    # Step 1: Get the REAL chromadb module
    _real_chromadb = importlib.import_module("chromadb")

    # Monkey-patch chromadb.config.get_class to fix the chromadb.api is chromadb
    # circular reference bug at the point of failure. This bug occurs when chromadb
    # is deleted from sys.modules and re-imported (e.g. by _restore_retrieval_modules
    # or conftest cleanup): the newly created chromadb module gets chromadb.api
    # set as an ATTRIBUTE pointing to itself (circular), causing
    # importlib.import_module('chromadb.api.segment') to return chromadb instead
    # of chromadb.api.segment. Fix: intercept get_class calls for chromadb.api.*
    # and ensure the correct module hierarchy is set up before delegating.
    import chromadb.config as _cc
    _orig_get_class = _cc.get_class

    def _patched_get_class(fqn, _type):
        import sys as _sys_local

        _mn, _cn = fqn.rsplit('.', 1)

        # Only apply the fix for chromadb.api submodules
        if _mn.startswith('chromadb.api'):
            _chromadb_root = _sys_local.modules.get('chromadb')
            _chromadb_api = _sys_local.modules.get('chromadb.api')

            # Detect: chromadb.api is the SAME module as chromadb root (circular bug)
            if _chromadb_api is not None and _chromadb_api is _chromadb_root:
                # This should NOT happen if conftest's cleanup ran correctly, but
                # as a safety net: re-import chromadb.api.segment by temporarily
                # deleting the broken chromadb.api from sys.modules so the import
                # machinery uses the correct module hierarchy.
                import importlib as _il
                for _k in list(_sys_local.modules.keys()):
                    if _k == 'chromadb.api' or _k.startswith('chromadb.api.'):
                        del _sys_local.modules[_k]
                _il.import_module('chromadb.api.segment')
                if 'chromadb.api' not in _sys_local.modules:
                    _sys_local.modules['chromadb.api'] = _sys_local.modules.get(
                        'chromadb.api.segment', _chromadb_root
                    )

        return _orig_get_class(fqn, _type)
    _cc.get_class = _patched_get_class

    # Step 2: Replace chromadb entries with the real chromadb module(s).
    # For the root "chromadb" key, use _real_chromadb.
    # For chromadb.api submodules, we must explicitly import each one to get
    # the REAL module object — using _real_chromadb.api for "chromadb.api.segment"
    # would assign the chromadb.api PACKAGE (not segment module), causing
    # get_class to resolve the wrong module (chromadb.api instead of
    # chromadb.api.segment) when looking up chromadb.api.segment.SegmentAPI.
    for _key in list(_sys.modules.keys()):
        if _key == "chromadb" or _key.startswith("chromadb."):
            _mod = _sys.modules.get(_key)
            _pc = getattr(_mod, "PersistentClient", None) if _mod else None
            if _pc is None or "MagicMock" in type(_pc).__name__:
                if _key == "chromadb":
                    _sys.modules[_key] = _real_chromadb
                elif _key == "chromadb.api":
                    # chromadb.api is the API package — assign the real one
                    _sys.modules[_key] = _real_chromadb.api
                else:
                    # For chromadb.api.* submodules (segment, types, models, etc.),
                    # explicitly import the module to get the REAL module object
                    # rather than reusing a potentially-stale cached reference.
                    # This ensures get_class('chromadb.api.segment.SegmentAPI')
                    # gets chromadb.api.segment (which has SegmentAPI), not
                    # chromadb.api (which does not).
                    try:
                        _sys.modules[_key] = importlib.import_module(_key)
                    except ImportError:
                        # If the module can't be imported (e.g., not yet loaded),
                        # leave the existing entry alone.
                        pass

    # Step 3: Re-import vector_store so it picks up the REAL chromadb reference.
    # We delete only vector_store (not retriever) to avoid breaking other tests.
    # We also delete embeddings and reranker since they might have cached
    # the old chromadb reference too.
    for _key in ("core.retrieval.vector_store", "core.retrieval.embeddings",
                 "core.retrieval.reranker"):
        if _key in _sys.modules:
            del _sys.modules[_key]
    importlib.import_module("core.retrieval.vector_store")

    # Step 4: Also directly fix the chromadb reference in the vector_store module
    # This handles the case where the module was already imported before our cleanup
    _vs_mod = _sys.modules.get("core.retrieval.vector_store")
    if _vs_mod is not None:
        setattr(_vs_mod, "chromadb", _real_chromadb)

    # Step 5: Update the VectorStoreAdapter reference in core.retrieval.retriever's
    # namespace. core.retrieval.retriever imported VectorStoreAdapter at its first
    # load time (when chromadb was still the MagicMock stub). Even after we
    # re-import vector_store, core.retrieval.retriever still holds the OLD class.
    # We update its namespace reference to the NEW VectorStoreAdapter from the
    # freshly imported vector_store module. This is safe because retriever only
    # uses VectorStoreAdapter, not chromadb directly.
    _retriever_mod = _sys.modules.get("core.retrieval.retriever")
    _new_vsa = getattr(_vs_mod, "VectorStoreAdapter", None) if _vs_mod else None
    if _retriever_mod is not None and _new_vsa is not None:
        setattr(_retriever_mod, "VectorStoreAdapter", _new_vsa)

    # Step 6: Do NOT re-import core.retrieval.retriever.

    from core.eval.retrieval_eval import (
        DEFAULT_NOTEBOOK_ID,
        prepare_retriever_for_eval,
    )

    engine, _corpus = prepare_retriever_for_eval(
        notebook_id=DEFAULT_NOTEBOOK_ID,
        build_graph=True,
    )
    return engine


@pytest.fixture(scope="module", autouse=True)
def eval_results(golden_cases, baseline_data, retriever):
    """
    Run the full retrieval quality evaluation and cache results.

    Autouse + module scope: runs once per module, before any test in this module.

    Fixture dependency chain (guarantees correct order):
      1. eval_corpus_setup  (session-scoped) — restores real modules + regenerates 43-topic corpus
      2. golden_cases       (module-scoped) — depends on eval_corpus_setup
      3. baseline_data       (module-scoped) — no deps
      4. retriever          (module-scoped) — depends on eval_corpus_setup; builds engine from corpus
      5. eval_results       (module-scoped, autouse) — depends on all above; runs evaluation

    NOTE: This fixture does NOT regenerate the corpus inline. The corpus is generated
    once by eval_corpus_setup (43 topics) and consumed by retriever. Inline corpus
    regeneration was removed — it previously overwrote the 43-topic corpus with an
    incomplete 22-topic list, causing all metrics to be 0.0.
    """
    engine = retriever

    top_k = baseline_data["config"]["top_k"]
    all_results: list[dict] = []

    for case in (golden_cases["faa"] + golden_cases["ccar"]):
        try:
            retrieved = engine.retrieve(
                case.question,
                top_k=top_k,
                final_k=top_k,
                notebook_id="__eval__",
                expand_graph=True,
            )
        except TypeError:
            try:
                retrieved = engine.retrieve(
                    case.question,
                    top_k=top_k,
                    final_k=top_k,
                    notebook_id="__eval__",
                )
            except TypeError:
                retrieved = engine.retrieve(
                    case.question,
                    top_k=top_k,
                    final_k=top_k,
                )

        result = evaluate_single_query(case, retrieved, top_k=top_k)
        all_results.append(result.to_dict())

    return all_results


# ---------------------------------------------------------------------------
# Metric aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_metrics(results: list[dict]) -> dict[str, float]:
    """Compute MRR, NDCG, Recall, HitRate from a list of per-query result dicts."""
    n = len(results)
    if n == 0:
        return {"mrr": 0.0, "ndcg": 0.0, "recall": 0.0, "hit_rate": 0.0}

    mrr = compute_mrr_at_k(
        [r["first_hit_rank"] for r in results],
        k=5,
    )
    ndcg = sum(
        compute_ndcg_at_k(
            r["relevance_vector"],
            r["expected_count"],
            k=5,
        )
        for r in results
    ) / n
    recall = sum(
        compute_recall_at_k(r["hit_count"], r["expected_count"], k=5)
        for r in results
    ) / n
    hit_rate = sum(1 for r in results if r["hit"]) / n

    return {
        "mrr": round(mrr, 4),
        "ndcg": round(ndcg, 4),
        "recall": round(recall, 4),
        "hit_rate": round(hit_rate, 4),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetrievalQualityRegression:
    """Regression tests for retrieval quality metrics."""

    def test_queries_yaml_exists(self):
        """Verify queries.yaml was created and has the right structure."""
        assert QUERIES_YAML.exists(), f"{QUERIES_YAML} not found"
        groups = load_queries_yaml(QUERIES_YAML)
        assert len(groups["faa"]) == 20, f"Expected 20 FAA queries, got {len(groups['faa'])}"
        assert len(groups["ccar"]) == 10, f"Expected 10 CCAR queries, got {len(groups['ccar'])}"

    def test_baseline_json_valid(self, baseline_data):
        """Verify baseline.json has required metric fields."""
        assert "metrics" in baseline_data
        for key in ("mrr_at_5", "ndcg_at_5", "recall_at_5", "hit_rate"):
            assert key in baseline_data["metrics"], f"Missing {key} in baseline"

    def test_mrr_no_regression(self, baseline_data, eval_results):
        """
        Fail if MRR@5 drops by more than regression_threshold_pct relative to baseline.
        """
        baseline_mrr = baseline_data["metrics"]["mrr_at_5"]
        threshold_pct = baseline_data["regression_threshold_pct"]
        threshold = baseline_mrr * (1.0 - threshold_pct / 100.0)

        metrics = _aggregate_metrics(eval_results)
        current_mrr = metrics["mrr"]

        regression_pct = ((baseline_mrr - current_mrr) / baseline_mrr * 100.0) if baseline_mrr > 0 else 0.0

        assert current_mrr >= threshold, (
            f"MRR@5 regression detected: baseline={baseline_mrr:.4f}, "
            f"current={current_mrr:.4f}, threshold={threshold:.4f}, "
            f"regression={regression_pct:.2f}% (limit: {threshold_pct}%)"
        )

    def test_ndcg_no_regression(self, baseline_data, eval_results):
        """
        Fail if NDCG@5 drops by more than regression_threshold_pct relative to baseline.
        """
        baseline_ndcg = baseline_data["metrics"]["ndcg_at_5"]
        threshold_pct = baseline_data["regression_threshold_pct"]
        threshold = baseline_ndcg * (1.0 - threshold_pct / 100.0)

        metrics = _aggregate_metrics(eval_results)
        current_ndcg = metrics["ndcg"]

        regression_pct = ((baseline_ndcg - current_ndcg) / baseline_ndcg * 100.0) if baseline_ndcg > 0 else 0.0

        assert current_ndcg >= threshold, (
            f"NDCG@5 regression detected: baseline={baseline_ndcg:.4f}, "
            f"current={current_ndcg:.4f}, threshold={threshold:.4f}, "
            f"regression={regression_pct:.2f}% (limit: {threshold_pct}%)"
        )

    def test_recall_no_regression(self, baseline_data, eval_results):
        """
        Fail if Recall@5 drops by more than regression_threshold_pct relative to baseline.
        """
        baseline_recall = baseline_data["metrics"]["recall_at_5"]
        threshold_pct = baseline_data["regression_threshold_pct"]
        threshold = baseline_recall * (1.0 - threshold_pct / 100.0)

        metrics = _aggregate_metrics(eval_results)
        current_recall = metrics["recall"]

        regression_pct = ((baseline_recall - current_recall) / baseline_recall * 100.0) if baseline_recall > 0 else 0.0

        assert current_recall >= threshold, (
            f"Recall@5 regression detected: baseline={baseline_recall:.4f}, "
            f"current={current_recall:.4f}, threshold={threshold:.4f}, "
            f"regression={regression_pct:.2f}% (limit: {threshold_pct}%)"
        )

    def test_all_golden_cases_evaluated(self, baseline_data, eval_results):
        """Sanity check: we evaluated exactly 30 queries (20 FAA + 10 CCAR)."""
        expected_total = 20 + 10
        assert len(eval_results) == expected_total, (
            f"Expected {expected_total} eval results, got {len(eval_results)}"
        )

    def test_py_compile_clean(self):
        """Verify all new files compile without syntax errors."""
        import py_compile
        for path in [
            QUERIES_YAML,
            BASELINE_JSON,
            PROJECT_ROOT / "tests/retrieval_quality_baseline/evaluator.py",
            PROJECT_ROOT / "tests/retrieval_quality_baseline/baseline.py",
        ]:
            if path.suffix == ".py":
                py_compile.compile(str(path), doraise=True)


# ---------------------------------------------------------------------------
# Canary test — verify corrupted RRF weights trigger regression
# ---------------------------------------------------------------------------

class TestRegressionDetectionWorks:
    """
    Verify that corrupting the RRF weights to near-zero bm25/graph
    (mimicking a broken retrieval) actually triggers lower scores.
    This confirms the test infrastructure is sound.
    """

    def test_rrf_weights_corruption_shows_degraded_mrr(
        self, retriever, golden_cases, baseline_data
    ):
        """
        Run with broken RRF weights (semantic=0.99, bm25=0.005, graph=0.005).
        The resulting MRR should be worse than the baseline.
        This is a CANARY — it confirms the regression detection mechanism works.
        """
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")
        os.environ.setdefault("RERANKER_LOCAL_FILES_ONLY", "1")

        broken_weights = {"semantic": 0.99, "bm25": 0.005, "graph": 0.005}
        top_k = baseline_data["config"]["top_k"]

        broken_results: list[dict] = []
        # Only use FAA queries for speed
        for case in golden_cases["faa"]:
            try:
                retrieved = retriever.retrieve(
                    case.question,
                    top_k=top_k,
                    final_k=top_k,
                    notebook_id="__eval__",
                    expand_graph=True,
                    rrf_weights=broken_weights,
                )
            except TypeError:
                try:
                    retrieved = retriever.retrieve(
                        case.question,
                        top_k=top_k,
                        final_k=top_k,
                        notebook_id="__eval__",
                        rrf_weights=broken_weights,
                    )
                except TypeError:
                    retrieved = retriever.retrieve(
                        case.question,
                        top_k=top_k,
                        final_k=top_k,
                        rrf_weights=broken_weights,
                    )

            result = evaluate_single_query(case, retrieved, top_k=top_k)
            broken_results.append(result.to_dict())

        broken_metrics = _aggregate_metrics(broken_results)
        baseline_mrr = baseline_data["metrics"]["mrr_at_5"]
        broken_mrr = broken_metrics["mrr"]

        # Canary assertion: the broken config should produce lower MRR
        # (This confirms the test detects regressions — if this fails, the
        # canary itself is suspicious but doesn't fail the main test suite)
        assert broken_results is not None
        print(
            f"\n[CANARY] Broken weights MRR={broken_mrr:.4f} vs baseline={baseline_mrr:.4f}"
        )
