# V4.0 Real-Corpus Retrieval Evaluation

## Corpus

- Source: `/Users/Zhuanz/AI-Notebooklm/data/docs/FAA_Part25.pdf`
- Vector corpus size: `1062` chunks already present in local Chroma
- Query set: `/Users/Zhuanz/AI-Notebooklm/docs/eval/part25_query_set.json`
- Query count: `12`

## Commands

Baseline evaluation:

```bash
cd /Users/Zhuanz/AI-Notebooklm
python3 scripts/evaluate_retrieval.py \
  --query-set docs/eval/part25_query_set.json \
  --top-k 8 \
  --final-k 5 \
  --output docs/eval/part25_eval_report.json
```

Best-weight replay:

```bash
cd /Users/Zhuanz/AI-Notebooklm
python3 scripts/evaluate_retrieval.py \
  --query-set docs/eval/part25_query_set.json \
  --top-k 8 \
  --final-k 5 \
  --rrf-weights 0,0.5,0.5 \
  --output docs/eval/part25_eval_best_weights.json
```

Weight search:

```bash
cd /Users/Zhuanz/AI-Notebooklm
python3 scripts/tune_rrf_weights.py \
  --query-set docs/eval/part25_query_set.json \
  --step 0.5 \
  --output docs/eval/part25_rrf_tuning.json
```

## Current Local Results

### Default retrieval settings

- `hit_rate = 0.5833`
- `top1_hit_rate = 0.3333`
- `page_hit_rate = 0.4167`
- `keyword_hit_rate = 0.5833`
- `mrr = 0.4333`

### Best tested weight set in this pass

- `rrf_weights = {"semantic": 0.0, "bm25": 0.5, "graph": 0.5}`
- `hit_rate = 0.8333`
- `top1_hit_rate = 0.8333`
- `page_hit_rate = 0.6667`
- `keyword_hit_rate = 0.8333`
- `mrr = 0.8333`

## Observations

- On this FAA Part 25 slice, lexical and graph signals were materially stronger than the semantic-only default.
- The best tested result tied BM25-only and BM25+graph-heavy configurations in the coarse `0.5` grid, so the harness is now in place for finer-grained follow-up rather than guessing.
- Two query families still miss under the current best tested setting:
  - lower-deck service compartment evacuation routes
  - fuel tank vent / outlet requirements

## Generated Artifacts

- `/Users/Zhuanz/AI-Notebooklm/docs/eval/part25_eval_report.json`
- `/Users/Zhuanz/AI-Notebooklm/docs/eval/part25_eval_best_weights.json`
- `/Users/Zhuanz/AI-Notebooklm/docs/eval/part25_rrf_tuning.json`

## Caveats

- This is a local FAA Part 25 evaluation slice, not yet the full COMAC intranet validation corpus.
- The reranker remains offline-first and may gracefully fall back to incoming candidate order if the local reranker weights are unavailable.
- The query set is intentionally compact and should be expanded before final production sign-off.
