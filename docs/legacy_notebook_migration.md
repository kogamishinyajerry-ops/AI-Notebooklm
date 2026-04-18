Legacy Notebook Ownership Migration (V4.2-T4)
==============================================

Audience: platform operators running the COMAC NotebookLM service on
a deployment that predates V3.3-P4 (which introduced per-principal
notebook ownership). This runbook walks you through migrating notebook
rows that carry `owner_id IS NULL` or `owner_id = ''` over to real
principals.

Script: `scripts/migrate_notebook_ownership.py`
Freeze pack: `docs/v4_2_t4_freeze_pack.md` (FD-1..FD-10)
Closes: Opus V3.3 F-4

-------------------------------------------------------------------------------
1. When to run this
-------------------------------------------------------------------------------
Run only if ALL of the following are true:

- You upgraded to `V3.3-P4` or later, which added `owner_id` to the
  `notebooks` table as a *nullable* column (existing rows stayed NULL).
- Multi-tenant auth is enabled in prod (`NOTEBOOKLM_API_KEYS` set).
- A query like
  `SELECT COUNT(*) FROM notebooks WHERE owner_id IS NULL OR owner_id = ''`
  returns > 0.

If auth is disabled, legacy rows are harmless — every request is
anonymous and the `owner_id` filter in `apps/api/main.py` is bypassed.

-------------------------------------------------------------------------------
2. Preflight
-------------------------------------------------------------------------------
a. **Back up the DB.** SQLite is a single file; copy it:

    cp data/notebooks.db data/notebooks.db.backup-$(date +%Y%m%d)

b. **Confirm the allowlist.** The script validates `--owner` against
   `NOTEBOOKLM_API_KEYS` before touching the DB:

    echo "$NOTEBOOKLM_API_KEYS" | tr ',' '\n'

c. **Run a read-only report first.** It never mutates anything:

    python scripts/migrate_notebook_ownership.py \
        --db data/notebooks.db \
        --report-only

Output shows total legacy rows, a `created_at`-year histogram, and the
first 10 notebook IDs. Use this to decide who the target owner should
be (often an "archive" principal that the operations team logs in as).

-------------------------------------------------------------------------------
3. Dry-run
-------------------------------------------------------------------------------
Always run a dry-run for the intended owner before the real pass:

    python scripts/migrate_notebook_ownership.py \
        --db data/notebooks.db \
        --owner ops-archive \
        --dry-run

Exit codes:
- `1` — there is pending work. Output lists each notebook_id, its
  current owner (`<null>` or `''`), and the target.
- `0` — nothing to migrate. Safe to stop here.
- `2` — validation failed (`--owner` not in allowlist, or env not set).
- `3` — I/O error (e.g. `--db` path does not exist).

-------------------------------------------------------------------------------
4. Real migration
-------------------------------------------------------------------------------
    python scripts/migrate_notebook_ownership.py \
        --db data/notebooks.db \
        --owner ops-archive \
        --assume-yes

Without `--assume-yes` the script prompts before writing. Drop the flag
for interactive runs.

What happens:
1. Script opens `data/notebooks.db`, executes `BEGIN IMMEDIATE`.
2. Every legacy row's `owner_id` is UPDATEd to the target.
3. Transaction commits. On ANY row failure the whole batch rolls back
   (exit 3) — you will not end up with a half-migrated table.
4. After commit, one audit row per migrated notebook is appended as
   `notebook.migrate_owner` via the system audit logger
   (`principal_id=system:migrate_notebook_ownership`).

Idempotency: re-running with the same `--owner` is a no-op. No new
audit rows are emitted for already-migrated notebooks.

-------------------------------------------------------------------------------
5. Targeted / surgical runs
-------------------------------------------------------------------------------
Migrate a specific notebook only:

    python scripts/migrate_notebook_ownership.py \
        --db data/notebooks.db \
        --owner alice \
        --notebook-id nb-1234 \
        --notebook-id nb-5678 \
        --assume-yes

Reassign a notebook from one principal to another (dangerous — must be
deliberate):

    python scripts/migrate_notebook_ownership.py \
        --db data/notebooks.db \
        --owner alice \
        --notebook-id nb-1234 \
        --force \
        --assume-yes

`--force` overwrites non-legacy `owner_id` values. Each overwrite emits
an audit row with `"migrate.forced": true` so the reassignment is
traceable.

-------------------------------------------------------------------------------
6. Verifying the result
-------------------------------------------------------------------------------
a. DB check:

    sqlite3 data/notebooks.db \
        "SELECT owner_id, COUNT(*) FROM notebooks GROUP BY owner_id"

   There should be zero `NULL` / empty-string owner rows unless you
   chose to only migrate a subset.

b. Audit check (tail the newest `notebook.migrate_owner` records):

    python scripts/audit_tail.py --event notebook.migrate_owner --limit 20

c. Integrity check: the audit log is append-only and has `INSTEAD OF
   DELETE`/`UPDATE` triggers (V4.2-T2). A tampered log is detected by
   `scripts/audit_integrity.py`.

-------------------------------------------------------------------------------
7. Exit code ladder
-------------------------------------------------------------------------------
| Code | Meaning                                                      |
|------|--------------------------------------------------------------|
| 0    | Success, or nothing to do.                                   |
| 1    | Dry-run found pending work. No writes happened.              |
| 2    | Validation failed (bad `--owner`, missing env, missing flag).|
| 3    | I/O or DB error. Transaction was rolled back.                |

-------------------------------------------------------------------------------
8. Rollback
-------------------------------------------------------------------------------
There is no "undo" flag. If you migrated rows to the wrong owner,
restore the preflight backup:

    cp data/notebooks.db.backup-YYYYMMDD data/notebooks.db

The append-only audit log keeps the migration records regardless —
they are historical evidence of what happened.

-------------------------------------------------------------------------------
9. Why this exists
-------------------------------------------------------------------------------
Before V3.3-P4, `notebooks` rows were single-tenant — there was no
`owner_id`. V3.3-P4 added the column as nullable to keep the migration
additive. V4.2-T3 hardened the admin surface. This script (V4.2-T4) is
the closing piece: the explicit, auditable, idempotent path to bring
legacy rows into the multi-tenant ownership model. Opus V3.3 F-4 is
now closed.
