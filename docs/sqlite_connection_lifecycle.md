# SQLite Connection Lifecycle (V4.3 A-1)

V4.3 A-1 introduces an optional stdlib-only SQLite connection pool behind
`NOTEBOOKLM_SQLITE_POOL_SIZE`.

## Default Behavior

Pooling is disabled by default:

```bash
unset NOTEBOOKLM_SQLITE_POOL_SIZE
```

With the default posture, `core.storage.sqlite_db.get_connection()` behaves as it
did before A-1: every call opens a fresh SQLite connection and caller-owned
`close()` closes it.

## Enabling the Pool

Set a positive integer to enable pooled idle connections per database path:

```bash
export NOTEBOOKLM_SQLITE_POOL_SIZE=4
```

Each returned connection is still caller-owned. Existing store code keeps using
the same pattern:

```python
conn = get_connection(db_path)
try:
    ...
finally:
    conn.close()
```

When pooling is enabled, `close()` returns an idle connection to the pool instead
of closing the underlying SQLite handle.

## Safety Rules

- C1: stdlib only, no daemon, no network, no telemetry.
- Every acquire applies WAL, `foreign_keys=ON`, `busy_timeout=5000`, and
  `synchronous=NORMAL`.
- Returning a connection rolls back any uncommitted transaction before reuse.
- Invalid or non-positive `NOTEBOOKLM_SQLITE_POOL_SIZE` disables pooling.
- `close_connection_pools()` closes idle pooled handles for tests or shutdown.

## Boundaries

This is a connection lifecycle hardening step, not a schema migration and not a
cross-process pool. Each Python worker owns its own in-process pool. SQLite still
coordinates file locking through WAL and busy timeout.

The existing caller-owned transaction contract remains intact. Code paths that
open explicit `BEGIN IMMEDIATE` transactions still own commit/rollback before
calling `close()`.
