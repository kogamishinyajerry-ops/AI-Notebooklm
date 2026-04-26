# Architectural Risk Register

Living log of known risks and drift concerns that cross feature boundaries.
Items stay here until resolved or explicitly retired with a decision record.

## Conventions

| Field | Meaning |
|---|---|
| **ID** | `R-<YYMM>-<nn>` — assigned when first logged. |
| **Severity** | P0 (blocks release) / P1 (accept w/ workaround) / P2 (watch). |
| **Detected** | First commit / PR / date where the risk was observed. |
| **Owner** | Agent or human accountable for the next action. |
| **Status** | Open / Mitigated / Resolved / Accepted. |

---

## R-2604-01 — Test-suite ordering fragility under partial runs

- **Severity:** P1
- **Detected:** 2026-04-18, observed on `main` @ `a8ae8dc` and reproduced on `19f97cd` (post V4.2-T4 merge).
- **Owner:** Claude Code (V4.3 W-V43-3)
- **Status:** **Resolved** (2026-04-18) — see Resolution section below. Entry retained for history.

### Symptom

Running this specific subset in a single `pytest` invocation produces 7 failures + 8 errors inside `tests/test_retrieval_quality.py` and `tests/test_retrieval_quality_regression.py`:

```
pytest tests/test_rate_limit.py tests/test_audit_log.py tests/test_audit_query.py \
       tests/test_fk_enforcement.py tests/test_sqlite_migration.py \
       tests/test_storage_concurrency.py \
       tests/test_retrieval_quality.py tests/test_retrieval_quality_regression.py
```

The same files pass individually, and the full-suite run (`pytest` with no file args) is green — 390 passed.

### Scope of confidence

- Full-suite green is the ground truth for C2 (citation pipeline) and C3 (merge preconditions). Historical sentinels per family are always run standalone in merge gates.
- The bug is **pre-existing on `main`**, not introduced by V4.2-T4. It reproduced cleanly at `a8ae8dc` before the T4 branch was merged.
- Likely cause is cross-test state leakage (shared SQLite path, leftover fixtures, monkeypatched env) between storage-heavy tests and the retrieval fixtures. Not yet root-caused.

### Why not fixed now

Touching retrieval-quality test plumbing risks perturbing the C2 sentinel, which is explicitly frozen for V4.2. The fix belongs in V4.3 where retrieval fixtures can be refactored safely.

### Mitigation

1. Merge gates run the **full suite** (`pytest`) — never custom subsets.
2. Historical sentinels are run **one family at a time** (T1 alone, T2 alone, …) to avoid the problematic ordering.
3. CI documentation must not teach contributors to run the above 8-file subset.

### Exit criteria

- Root cause identified (likely an autouse fixture scope or `data/notebooks.db` shared path).
- Subset and full suite both green under any file ordering.
- Move entry to `## Resolved` section with fix commit hash.

### Resolution (2026-04-18)

- **Root cause (confirmed — not speculative):** five test modules —
  `test_rate_limit.py`, `test_auth_isolation.py`, `test_observability.py`,
  `test_llm_health.py`, `test_studio.py` — each conditionally install a
  stub `core.retrieval.retriever` module guarded by
  `if "core.retrieval.retriever" not in sys.modules`. The stub replaces
  `RetrieverEngine` with a `_FakeRetrieverEngine` that lacks `_rrf_fuse`.
- **Why the full suite passed by accident:** alphabetical ordering put at
  least one test that imports the *real* `core.retrieval.retriever` before
  the stubbers, so their guards skipped. The 8-file subset broke that
  accident: nothing upstream imported the real module, so the first stubber
  won the race and poisoned every downstream retrieval test with the
  attribute-less `_FakeRetrieverEngine`.
- **Fix:** `tests/conftest.py` now pre-imports `core.retrieval.retriever`
  at conftest module-load time (same pattern it already uses for
  `torch`, `transformers`, `sentence_transformers`, and
  `core.ingestion.transaction`). Result: every stubber's guard finds the
  real module and skips — the subset passes under any ordering.
- **Why not fix the test files instead:** five identical copies of the
  guard exist in five files; fixing them individually is churn and future
  regressions are likely. The conftest-level pre-import is a single
  load-bearing line that makes the stubbers self-skip.
- **Evidence:**
  - 8-file subset (previously 7 fail + 8 error): now **114 passed**.
  - Full suite: **390 passed** (unchanged).
  - C2 retrieval sentinel: **8 passed** (unchanged).

### Regression sentinel follow-up (2026-04-23)

- `tests/test_r2604_isolation_sentinel.py` now re-runs the historical
  eight-file R-2604 subset in a fresh child process and asserts the collected
  test count matches the passed count.
- The sentinel inherits the ambient environment instead of hardcoding a mode,
  so the same guard is exercised under both the default suite and the
  `NOTEBOOKLM_SQLITE_POOL_SIZE=4` suite.
- **Fresh PR #57 evidence:**
  - Full suite: **426 passed**.
  - Pool-enabled full suite: **426 passed**.
  - C2 retrieval sentinel: **8 passed**.
  - Historical sentinels (five families, run separately): **117 passed**.
  - Raw historical eight-file subset: **126 passed**.

---

## R-2604-02 — V4.2-T3 review provenance wording drift

- **Severity:** P2
- **Detected:** 2026-04-20 Codex takeover audit of V4.2 PR history.
- **Owner:** Codex GPT-5.4 (V4.3 W-V43-5)
- **Status:** **Mitigated** by retrospective Codex supplement review and
  W-V43-5 audit documentation; retained until Kogami next deep acceptance.

### Symptom

PR #42 shipped V4.2-T3 Admin Role & Dashboard with self-signed
external-review wording in the PR body. The wording blurred the boundary
between executor self-verification and independent terminal review.

### Scope of confidence

- This is a governance provenance finding, not a direct runtime defect.
- The T3 code surface has dedicated admin, audit-query, quota-admin,
  dashboard, rate-limit, and retrieval sentinel coverage.
- Historical Claude Code review rows and PR bodies must remain unchanged.

### Mitigation

1. Created a Codex supplement review row in Notion for PR #42.
2. Added `docs/v4_3_codex_retro_governance_audit.md` as the repo-side audit
   artifact for V4.2 PR #39/#40/#41/#42.
3. Future Codex PR bodies use `Self-verification checklist` wording and do not
   represent executor self-review as independent terminal review.

### Exit criteria

- W-V43-5 audit PR merged and GitHub issue #44 closed.
- Notion W-V43-5 task marked Succeeded with self-review verification attached.
- Kogami next deep acceptance acknowledges the retrospective audit trail.

---

## R-2604-03 — Window-2 Codex review coverage gap (PR #53, #54, #55)

- **Severity:** P0 (process integrity), P2 (runtime — no observed defect at merge time)
- **Detected:** 2026-04-26 during Window-2 closeout audit (`docs/v4_3_window_2_reconciliation.md` §5).
- **Owner:** Codex GPT-5.4 (W-V43-11)
- **Status:** **Mitigated** (2026-04-26). Retained until Kogami next deep acceptance acknowledges the retrospective audit trail.

### Symptom

Three Window-2 PRs merged without the Codex review their CLAUDE.md hard-rule trigger required:

| PR | CLAUDE.md trigger | Codex at merge |
|---|---|---|
| #53 (W-V43-7 multi-worker rate-limit) | "API 契约 / adapter boundary >5 LOC" | None |
| #54 (W-V43-8 admin bypass) | "API 契约 / adapter boundary" (borderline) | None |
| #55 (W-V43-demo) | **double trigger** — multi-frontend + UI flow change | None |

PR #56 was correctly reviewed by `chatgpt-codex-connector`, demonstrating the workflow is operational; the gap was procedural, not infrastructural.

### Why this matters

PR #55 is the largest single-PR delta in V4.3 (+4881/−1132 LOC). Self-verification alone is below the project's stated governance bar for that category of change. Without retrospective audit, the PR's risk surface is unmapped.

### Mitigation (W-V43-11, this PR)

- `docs/v4_3_w11_codex_window2_audit.md` collects retrospective Codex findings and executor reading notes.
- Codex independent verdicts:
  - **PR #55**: CHANGES_REQUIRED (2 HIGH, 3 MEDIUM, 1 LOW)
  - **PR #54**: APPROVE WITH FOLLOW-UPS (1 LOW)
  - **PR #53**: APPROVE WITH FOLLOW-UPS (2 MEDIUM, 1 LOW)
- The two HIGH findings on PR #55 (advisory verification gate; unscoped chat allowing demo-seed bleed) become first-class Window-3 work items (W-V43-11.1, W-V43-11.2). Both pre-date PR #55 — they are not Window-2 regressions — but PR #55 widened the exploit surface of the verification advisory gap.
- Three MEDIUM PR #55 items (provider drift in audit trail, MiniMax operator visibility, loopback-only restriction) become Window-3 governance work items.
- PR #53 / #54 follow-ups are smaller hardening items (W-V43-11.7-9).

### Exit criteria

- W-V43-11 audit PR merged.
- Codex Notion supplement review rows created for PRs #53, #54, #55. _(operator step)_
- W-V43-11.1 and W-V43-11.2 remediation PRs landed before any new Window-3 user-facing PR. _(forward-looking)_
- Move R-2604-03 to Resolved after Kogami next deep acceptance acknowledges the retrospective audit trail.

---

## R-2604-04 — C2 retrieval-quality baseline is hardware-locked

- **Severity:** P2 (process integrity — sentinel can pass on one machine and fail on another for the same code)
- **Detected:** 2026-04-26 during Window-2 closeout fresh-worktree pytest (`docs/v4_3_window_2_reconciliation.md` §6 + §4.5).
- **Owner:** Claude Code (W-V43-13 partial; engine-layer Option B deferred to Window 5+)
- **Status:** Mitigated (metric layer); engine-layer reproducibility deferred

### Symptom

`tests/test_retrieval_quality_regression.py::test_mrr_no_regression` fails deterministically on a fresh Apple Silicon worktree at:
- pre-Window-2 commit `30c22f6`: MRR@5=0.3383, 11.99% drift from baseline=0.3844
- post-Window-2 commit `53a5fe2`: MRR@5=0.3539, 7.93% drift from baseline=0.3844
- threshold: 5% maximum drift

The same test passes on the executor's recording environment. Window 2 narrowed the drift by 4 pp; the regression itself pre-dates Window 2.

### Why this matters

A merge gate that fails on a co-developer's machine and passes on the canonical executor's machine is governance-fragile. Independent verification of the `8 passed` C2 sentinel claim becomes impossible without the executor's exact environment.

### Mitigation (W-V43-13, partial — landed 2026-04-26)

Three options were considered (`docs/v4_3_window_2_reconciliation.md` §4.5):
- **A.** Pin embedding model file format (force `safetensors` over `pytorch_model.bin`); assert tokenizer hash at sentinel boot.
- **B.** Checkpoint pre-computed embeddings as a fixture artifact (small JSON or NPZ committed); sentinel runs against frozen vectors. **Recommended** as the cleanest C1-compliant fix.
- **C.** Relax regression threshold to a hardware-aware floor (compare against previous commit's measured MRR rather than a frozen baseline). Trades sentinel sharpness.

W-V43-13 landed the **metric-layer slice of Option B** as
`tests/test_retrieval_metric_canonical.py` + `docs/RETRIEVAL_QUALITY_BASELINE.md`. The metric primitives in `tests/retrieval_quality_baseline/evaluator.py` are now sentinel-protected against drift via the canonical `per_query_summary` in `baseline.json` — pure-Python, hardware-independent, runs in ms.

The **full Option B** (mocking ChromaDB HNSW + EmbeddingManager so the live-pipeline test consumes frozen vectors instead of running the engine) is genuinely larger than a single PR and is deferred. The metric-layer sentinel buys diagnostic clarity in the meantime: when the live test fails on a new machine, the operator can run the metric sentinel separately to confirm the drift is engine-layer (hardware) rather than metric-layer (code).

### Exit criteria

- ✅ Metric-layer determinism documented in `docs/RETRIEVAL_QUALITY_BASELINE.md` and sentinel-protected.
- ✅ `baseline.json` self-consistency sentinel-protected.
- ⏳ `test_mrr_no_regression` passes on at least two distinct machines (executor + a fresh Apple Silicon Mac) at the same commit. _(blocked on full Option B; out of scope for W-V43-13)_

---

## Resolved

- R-2604-01 (2026-04-18, fix commit on branch `fix/v4-3-test-isolation-r2604-01`; sentinel-protected by PR #57 as of 2026-04-23).
