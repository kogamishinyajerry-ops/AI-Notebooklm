# V4.3 W-V43-2 V4.1 Should-Checklist Cleanup

**Date:** 2026-04-20
**Owner:** Codex GPT-5.4
**Task:** W-V43-2
**Decision:** Close the orphan V4.1b pointer by disposition, not by creating a
new historical phase.

## Why This Exists

The V4.1 phase row ended with this next-phase pointer:

```text
V4.1b: Prometheus /metrics + Should-item cleanup -> V4.2
```

No standalone V4.1b phase row ever reached `main`. V4.2 started directly after
V4.1, and V4.3 later absorbed the remaining V4.1b items as explicit W-V43 tasks.

This document closes that orphan pointer without modifying V4.1's historical
Notion record.

## Closure Matrix

| Item | Origin | Disposition | Evidence |
|---|---|---|---|
| V4.1-T3 Prometheus metrics | V4.1 initial plan and V4.1b child page | Closed in V4.3 | PR #49, `docs/METRICS_GUIDE.md`, `tests/test_metrics.py` |
| M1 storage concurrency test | V4.1 review must-fix | Closed in V4.1 | PR #38, `tests/test_storage_concurrency.py` |
| M2 migration counter accuracy | V4.1 review must-fix | Closed in V4.1 | `core/storage/sqlite_db.py` uses `cursor.rowcount` for `INSERT OR IGNORE` counters |
| M3 Notion V4.1 risk record | V4.1 review must-fix | Closed in V4.1 | V4.1 phase page records all review findings and Round 2 approval |
| G-2 corrupted JSON rollback assertion | V4.1 review should item | Closed in W-V43-2 | `tests/test_sqlite_migration.py::test_corrupted_json_causes_migration_failure` now asserts source JSON files remain and no `.v4_1_migrated` backups are produced on failure |
| G-3 retrieval fixture sys.modules hack | V4.1 review tech debt | Closed in V4.3 | PR #47, `docs/architectural_risk_register.md` R-2604-01 resolution |
| F-4 NoteStore FK enforcement gap | V4.1 Round 2 finding | Closed in V4.2 | PR #41, `docs/FK_ENFORCEMENT_GUIDE.md`, `tests/test_fk_enforcement.py` |
| F-2 explicit SQLite transaction mode | V4.1 review should item | Deferred to A-1 | Current code is stable under full suite and storage sentinels; changing connection isolation policy belongs with the SQLite connection-pool/transaction-policy task, not this cleanup PR |
| F-3 orphan JSON startup scan | V4.1 review should item | Accepted, no immediate code change | Failed migrations do not rename/delete JSON files; W-V43-2 adds direct assertions. Post-commit crash cleanup remains a low-probability legacy-migration hardening concern |
| A-1 SQLite connection pool | V4.1/V4.3 candidate | Remains open | Next heavy technical task candidate after V4.1b cleanup |

## What W-V43-2 Changes

W-V43-2 intentionally keeps the code change small:

- Adds explicit regression assertions to the corrupted JSON migration test.
- Adds this closure artifact so V4.1b is no longer an ambiguous missing phase.
- Preserves the V4.1 Notion `Next Phase Pointer` as historical context.

## What W-V43-2 Does Not Change

- No runtime storage transaction semantics are changed.
- No SQLite connection-pool behavior is introduced.
- No citation, retrieval, auth, quota, audit, or FK migration files are modified.
- No dependency manifest is modified.

## A-1 Handoff

The only remaining non-closed technical concern from the V4.1b cluster is A-1:
SQLite connection lifecycle and transaction policy. It should be handled as a
dedicated V4.3 technical PR because it may affect request latency, lock behavior,
test isolation, and transaction ownership across stores.

Recommended A-1 entry checks:

- Keep `requirements.txt` unchanged.
- Preserve `PRAGMA foreign_keys=ON`, WAL, busy timeout, and append-only audit
  invariants.
- Run storage concurrency, FK, audit, rate-limit, migration, and full-suite tests
  before merge.
- Do not change V4.2 frozen files unless the PR body includes a precise Frozen
  File Override.

## Decision

The V4.1b pointer is closed for project-tracking purposes. V4.3 can proceed to
the heavier technical workstream with A-1 still explicitly open, not hidden
inside the old V4.1 should-list.
