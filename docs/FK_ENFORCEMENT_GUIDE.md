# V4.2-T5 SQLite Foreign Key Enforcement Guide

This guide documents the V4.2-T5 data-integrity layer for COMAC NotebookLM.
It is C1 compliant: SQLite only, no network calls, no telemetry, and no new
Python dependencies.

## Scope

V4.2-T5 makes existing SQLite foreign keys enforceable on every connection and
repairs historical orphan rows before the migration rebuilds tables.

This task does not add HTTP routes, does not change citation XML, and does not
touch retrieval behavior.

## FK Matrix

| Parent table | Child table | Child FK column | Delete behavior |
| --- | --- | --- | --- |
| `notebooks.id` | `notes.notebook_id` | `notebook_id` | `ON DELETE CASCADE` |
| `notebooks.id` | `sources.notebook_id` | `notebook_id` | `ON DELETE CASCADE` |
| `notebooks.id` | `chat_messages.notebook_id` | `notebook_id` | `ON DELETE CASCADE` |
| `notebooks.id` | `studio_outputs.notebook_id` | `notebook_id` | `ON DELETE CASCADE` |
| `notebooks.id` | `knowledge_graphs.notebook_id` | `notebook_id` | `ON DELETE CASCADE` |

## Runtime Behavior

Every connection returned by `core.storage.sqlite_db.get_connection()` enables:

```sql
PRAGMA foreign_keys=ON;
```

The notebook-scoped stores no longer disable FK enforcement. Creating a note,
source, chat message, studio output, or knowledge graph for a missing notebook
is rejected by SQLite and translated to:

```text
404 Notebook not found: <notebook_id>
```

Deleting a notebook cascades child rows in SQLite. Application code should not
manually delete child rows as part of notebook deletion.

Future SQLite-backed stores must use `core.storage.sqlite_db.get_connection()`.
Direct `sqlite3.connect(...)` calls do not inherit the project FK settings.

## Migration

The migration lives in:

```text
core/storage/migrations/v4_2_t5_fk_enforcement.py
```

It is tracked with:

```sql
PRAGMA user_version=1;
```

The migration uses an idempotent table rebuild pattern:

1. Run orphan repair before rebuilding.
2. Temporarily disable FK checks for the rebuild transaction.
3. Rebuild `notebooks`, `notes`, `sources`, `chat_messages`, `studio_outputs`, and `knowledge_graphs`.
4. Restore each table's explicit indexes from `sqlite_master`.
5. Run `PRAGMA foreign_key_check`.
6. Set `user_version=1`.
7. Re-enable `PRAGMA foreign_keys=ON`.

If `foreign_key_check` reports violations, the transaction rolls back and startup
fails rather than silently preserving inconsistent data.

## Repair SOP

Use the local repair script for manual checks or one-off repair:

```bash
python3 scripts/audit_integrity.py --db data/notebooks.db --check
python3 scripts/audit_integrity.py --db data/notebooks.db --repair
python3 scripts/audit_integrity.py --db data/notebooks.db --repair --confirm
```

`--check` prints orphan counts and exits non-zero when any orphan exists.

`--repair` prompts for confirmation.

`--repair --confirm` runs non-interactively and is the mode used by the migration
pre-hook.

Each deleted orphan emits a T2 audit event:

```text
integrity.repair
```

The event payload contains only:

```json
{
  "orphan_table": "notes",
  "orphan_id": "example-id",
  "parent_table": "notebooks",
  "parent_column": "id"
}
```

No note content, chat text, studio output text, source file content, or citation
XML is recorded.

## Manual Integrity Checks

To verify a database directly:

```bash
sqlite3 data/notebooks.db 'PRAGMA foreign_keys;'
sqlite3 data/notebooks.db 'PRAGMA foreign_key_check;'
sqlite3 data/notebooks.db 'PRAGMA user_version;'
```

Expected values after T5:

```text
foreign_keys = 1
foreign_key_check = no rows
user_version = 1
```

## Troubleshooting

If startup fails during migration, first run:

```bash
python3 scripts/audit_integrity.py --db data/notebooks.db --check
```

If orphan rows are reported and this is an expected legacy database, run:

```bash
python3 scripts/audit_integrity.py --db data/notebooks.db --repair --confirm
```

Then restart the API. If `PRAGMA foreign_key_check` still reports rows after
repair, stop and inspect the table names before changing schema behavior.

If high write concurrency produces `SQLITE_BUSY`, remember that notebook delete
operations now cascade through all child tables in one SQLite write transaction.
Check WAL health and checkpoint behavior before changing FK settings.

Audit logs contain the explicit parent action, such as `notebook.delete`.
SQLite CASCADE side effects do not emit one audit event per child row.
