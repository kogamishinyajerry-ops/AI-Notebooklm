from __future__ import annotations

from core.eval.retrieval_eval import (
    RetrievalEvalCase,
    build_eval_corpus,
    evaluate_cases,
    evaluate_weight_grid,
    weight_grid,
)


class _StubRetriever:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def retrieve(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return list(self.payloads.get(query, []))


def test_build_eval_corpus_attaches_ids_to_metadata():
    corpus = build_eval_corpus(
        {
            "ids": ["chunk-1"],
            "documents": ["bird strike requirement"],
            "metadatas": [{"page": 78, "source": "FAA_Part25.pdf"}],
        }
    )

    assert corpus == [
        {
            "text": "bird strike requirement",
            "metadata": {
                "page": 78,
                "source": "FAA_Part25.pdf",
                "id": "chunk-1",
            },
        }
    ]


def test_evaluate_cases_reports_hit_rate_and_mrr():
    retriever = _StubRetriever(
        {
            "bird strike": [
                {"text": "§ 25.631 Bird strike damage", "metadata": {"page": 78, "source": "FAA_Part25.pdf"}},
            ],
            "parking brake": [
                {"text": "parking brake control requirement", "metadata": {"page": 86, "source": "FAA_Part25.pdf"}},
            ],
        }
    )
    cases = [
        RetrievalEvalCase(query="bird strike", expected_pages=[78], expected_keywords=["bird strike damage"]),
        RetrievalEvalCase(query="parking brake", expected_pages=[86], expected_keywords=["parking brake"]),
    ]

    report = evaluate_cases(retriever, cases, expand_graph=False)

    assert report["summary"]["hit_rate"] == 1.0
    assert report["summary"]["top1_hit_rate"] == 1.0
    assert report["summary"]["mrr"] == 1.0
    assert len(retriever.calls) == 2


def test_evaluate_weight_grid_orders_best_candidate_first():
    retriever = _StubRetriever(
        {
            "stall": [
                {"text": "stall warning requirement", "metadata": {"page": 1, "source": "FAA_Part25.pdf"}},
            ]
        }
    )
    cases = [RetrievalEvalCase(query="stall", expected_pages=[1], expected_keywords=["stall warning"])]

    rankings = evaluate_weight_grid(
        retriever,
        cases,
        candidates=[
            {"semantic": 0.5, "bm25": 0.5, "graph": 0.0},
            {"semantic": 0.2, "bm25": 0.2, "graph": 0.6},
        ],
        expand_graph=False,
    )

    assert rankings[0]["mrr"] == 1.0
    assert rankings[0]["hit_rate"] == 1.0


def test_weight_grid_enumerates_normalized_candidates():
    candidates = weight_grid(step=0.5)

    assert {"semantic": 0.5, "bm25": 0.5, "graph": 0.0} in candidates
    assert {"semantic": 0.0, "bm25": 0.0, "graph": 1.0} in candidates
    assert all(abs(sum(item.values()) - 1.0) < 1e-9 for item in candidates)
