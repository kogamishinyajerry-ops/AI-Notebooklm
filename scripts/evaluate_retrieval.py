from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.eval.retrieval_eval import (
    DEFAULT_NOTEBOOK_ID,
    evaluate_cases,
    load_eval_cases,
    prepare_retriever_for_eval,
    write_json_report,
)


DEFAULT_QUERY_SET = Path("docs/eval/part25_query_set.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation on the local corpus.")
    parser.add_argument("--query-set", default=str(DEFAULT_QUERY_SET), help="Path to the labeled query set JSON file.")
    parser.add_argument("--output", help="Optional JSON output path for the full evaluation report.")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument("--no-graph", action="store_true", help="Disable graph expansion during evaluation.")
    parser.add_argument(
        "--rrf-weights",
        help="Optional semantic,bm25,graph weights. Example: 0.4,0.3,0.3",
    )
    return parser.parse_args()


def parse_weights(raw: str | None) -> dict[str, float] | None:
    if not raw:
        return None
    semantic, bm25, graph = [float(item.strip()) for item in raw.split(",")]
    return {"semantic": semantic, "bm25": bm25, "graph": graph}


def main() -> int:
    args = parse_args()

    os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")
    os.environ.setdefault("RERANKER_LOCAL_FILES_ONLY", "1")

    retriever, corpus = prepare_retriever_for_eval(
        notebook_id=DEFAULT_NOTEBOOK_ID,
        build_graph=not args.no_graph,
    )
    cases = load_eval_cases(args.query_set)
    report = evaluate_cases(
        retriever,
        cases,
        top_k=args.top_k,
        final_k=args.final_k,
        notebook_id=DEFAULT_NOTEBOOK_ID,
        expand_graph=not args.no_graph,
        rrf_weights=parse_weights(args.rrf_weights),
    )
    report["summary"]["corpus_chunks"] = len(corpus)
    report["summary"]["query_set"] = str(Path(args.query_set))

    if args.output:
        write_json_report(args.output, report)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
