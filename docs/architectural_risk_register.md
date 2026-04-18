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
- **Owner:** Claude Code (V4.3 planning scope)
- **Status:** Open — accepted for V4.2 release

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

---

## Resolved

_(none yet)_
