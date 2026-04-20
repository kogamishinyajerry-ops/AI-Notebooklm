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

## Resolved

- R-2604-01 (2026-04-18, fix commit on branch `fix/v4-3-test-isolation-r2604-01`).
