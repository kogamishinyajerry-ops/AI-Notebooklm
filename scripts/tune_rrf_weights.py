from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.eval.retrieval_eval import (
    DEFAULT_NOTEBOOK_ID,
    evaluate_weight_grid,
    load_eval_cases,
    prepare_retriever_for_eval,
    weight_grid,
    write_json_report,
)


DEFAULT_QUERY_SET = Path("docs/eval/part25_query_set.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search RRF weight candidates on the local corpus.")
    parser.add_argument("--query-set", default=str(DEFAULT_QUERY_SET), help="Path to the labeled query set JSON file.")
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument("--step", type=float, default=0.2, help="Grid search step size; must evenly divide 1.0.")
    parser.add_argument("--limit", type=int, default=5, help="How many top candidates to print.")
    parser.add_argument("--no-graph", action="store_true", help="Disable graph expansion during tuning.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")
    os.environ.setdefault("RERANKER_LOCAL_FILES_ONLY", "1")

    retriever, corpus = prepare_retriever_for_eval(
        notebook_id=DEFAULT_NOTEBOOK_ID,
        build_graph=not args.no_graph,
    )
    cases = load_eval_cases(args.query_set)
    rankings = evaluate_weight_grid(
        retriever,
        cases,
        candidates=weight_grid(step=args.step),
        top_k=args.top_k,
        final_k=args.final_k,
        notebook_id=DEFAULT_NOTEBOOK_ID,
        expand_graph=not args.no_graph,
    )

    report = {
        "summary": {
            "query_set": str(Path(args.query_set)),
            "corpus_chunks": len(corpus),
            "candidates": len(rankings),
            "best_weights": rankings[0]["weights"] if rankings else None,
            "best_mrr": rankings[0]["mrr"] if rankings else None,
            "best_hit_rate": rankings[0]["hit_rate"] if rankings else None,
            "top_k": args.top_k,
            "final_k": args.final_k,
            "step": args.step,
            "expand_graph": not args.no_graph,
        },
        "rankings": rankings,
    }

    if args.output:
        write_json_report(args.output, report)

    print(json.dumps({"summary": report["summary"], "top": rankings[: args.limit]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
