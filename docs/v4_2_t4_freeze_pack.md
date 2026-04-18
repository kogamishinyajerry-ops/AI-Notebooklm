V4.2-T4 — Legacy Notebook Migration · Freeze Pack
===================================================

Status: **FROZEN 2026-04-18** (Executor=Gate, Opus 4.7)
Depends on: V4.2-T3 (merged PR #42, a8ae8dc)
Gap closed: Opus V3.3 F-4 — legacy notebooks with `owner_id IS NULL`
have no migration path.

Goal
----
Deliver `scripts/migrate_notebook_ownership.py`: an idempotent CLI that
assigns an `owner_id` to legacy notebook rows (created before V3.3-P4
introduced per-principal ownership), with dry-run, principal validation,
per-row audit emission, and explicit exit codes.

Frozen Decisions
----------------
- **FD-1 · CLI contract**  
  `python scripts/migrate_notebook_ownership.py --db PATH --owner PRINCIPAL_ID [flags]`  
  Flags: `--dry-run`, `--report-only`, `--notebook-id ID` (repeatable),
  `--force` (overwrite non-null), `--assume-yes` (skip prompt).

- **FD-2 · Legacy definition**  
  A row is *legacy* iff `owner_id IS NULL OR owner_id = ''`. The empty
  string case exists because V3.3-P4 allowed a nullable column and a few
  ingestion paths normalized to `""`.

- **FD-3 · Idempotency**  
  Re-running with the same `--owner` MUST be safe. Non-legacy rows are
  skipped silently unless `--force` is given. Running twice produces no
  duplicate audit rows for rows already migrated.

- **FD-4 · Principal validation**  
  `--owner` MUST be present in `NOTEBOOKLM_API_KEYS` allowlist
  (principal_id side of `principal:key`). Unknown principal → exit 2,
  no DB writes, no audit emission.

- **FD-5 · Dry-run semantics**  
  `--dry-run` prints per-row plan (notebook_id, name, current owner_id,
  target owner_id) and exits 1 when there is pending work, 0 when empty.
  No DB writes, no audit emission.

- **FD-6 · Report-only semantics**  
  `--report-only` prints a summary (total legacy, grouped by year of
  `created_at`, sample of first 10 IDs) and always exits 0.

- **FD-7 · Transactional safety**  
  The migration runs inside a single `BEGIN IMMEDIATE` transaction. On
  any row failure the transaction rolls back entirely (no partial
  migration) and the CLI exits 3.

- **FD-8 · Audit emission**  
  New event `notebook.migrate_owner` (value; enum name `NOTEBOOK_MIGRATE_OWNER`).  
  One audit row per successfully migrated notebook. `actor_type=system`,
  `principal_id=system:migrate_notebook_ownership`, `resource_type=notebook`,
  `resource_id=<notebook_id>`, `http_status=200`, payload includes
  `migrate.from_owner`, `migrate.to_owner`, `migrate.forced` (bool).
  Emission goes through `AuditLogger.for_system("migrate_notebook_ownership")`.

- **FD-9 · Zero dependency additions (C1)**  
  Script uses stdlib only: `argparse`, `sqlite3`, `os`, `sys`. Reuses
  `core.storage.sqlite_db.get_connection`, `core.governance.audit_logger`,
  `core.security.auth.load_api_keys` (already present).

- **FD-10 · Exit code ladder**  
  `0` = success / nothing to do;  
  `1` = dry-run found pending work (no writes happened);  
  `2` = validation failed (unknown principal, no `NOTEBOOKLM_API_KEYS`,
        missing `--owner`);  
  `3` = I/O or DB error (rolled back).

File Plan
---------
- **NEW** `scripts/migrate_notebook_ownership.py` (~200 lines)
- **NEW** `tests/test_migrate_notebook_ownership.py` (~15 cases)
- **EDIT** `core/governance/audit_events.py` (+1 enum member)
- **EDIT** `core/governance/audit_redact.py` (+3 allowed fields)
- **EDIT** `tests/test_audit_log.py` (enum completeness assertion)
- **NEW** `docs/legacy_notebook_migration.md` (~100 lines operator guide)

Execution Order
---------------
1. **Step 1** — Audit surface: `NOTEBOOK_MIGRATE_OWNER` enum member +
   redact whitelist entries + enum-completeness test update.
2. **Step 2** — `--report-only` path (no mutation, read-only summary).
3. **Step 3** — `--dry-run` path (plan emission, exit 1 on pending).
4. **Step 4** — Real migration path with principal validation +
   transactional write + per-row audit emission + `--force` +
   `--notebook-id` filter.
5. **Step 5** — Operator runbook `docs/legacy_notebook_migration.md`.
6. **Step 6** — Final sentinel: full suite green + retrieval-quality
   regression 8/8, then open PR.

Test Plan
---------
- `test_report_only_lists_legacy_rows`
- `test_report_only_exits_zero_when_empty`
- `test_dry_run_prints_plan_and_exits_1`
- `test_dry_run_no_db_writes`
- `test_dry_run_no_audit_emission`
- `test_migrate_assigns_owner_to_legacy_rows`
- `test_migrate_idempotent_second_run_is_noop`
- `test_migrate_skips_non_legacy_without_force`
- `test_migrate_force_overwrites_non_legacy`
- `test_migrate_empty_string_owner_treated_as_legacy`
- `test_migrate_filters_by_notebook_id`
- `test_migrate_unknown_principal_exits_2`
- `test_migrate_missing_api_keys_exits_2`
- `test_migrate_emits_audit_row_per_notebook`
- `test_migrate_rolls_back_on_row_failure`

Stop Conditions
---------------
1. All new tests pass + previous 362-test baseline remains green.
2. Retrieval-quality regression (`tests/eval/retrieval_quality_test.py`)
   still 8/8 — C2 preserved.
3. No new third-party dependency added — C1 preserved.
4. PR branch `feat/v4-2-t4-legacy-notebook-migration` opened, Gate
   Review body self-signed (Executor=Gate).

Threat Model Notes
------------------
- **T4-Threat-1 · Privilege escalation via migrate**  
  Mitigation: FD-4 validates `--owner` ∈ `NOTEBOOKLM_API_KEYS` — cannot
  assign to a principal that cannot authenticate.
- **T4-Threat-2 · Silent overwrite of legitimate owner**  
  Mitigation: FD-3 + FD-8 — `--force` required to overwrite, each
  overwrite emits an audit row with `migrate.forced=true`.
- **T4-Threat-3 · Partial migration leaving inconsistent state**  
  Mitigation: FD-7 single-transaction with rollback.
- **T4-Threat-4 · Accidental run against prod DB**  
  Mitigation: FD-5 dry-run default posture, FD-6 report-only, operator
  runbook explicit about `--db` path.
