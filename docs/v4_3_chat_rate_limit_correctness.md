# V4.3 W-V43-7: Multi-Worker Chat Rate-Limit Correctness

## Problem

`core/governance/rate_limit.py` previously rebuilt slowapi with a fresh
in-memory `MemoryStorage()` on every app setup. That kept full-suite tests
isolated, but it also meant each worker process had its own chat bucket. In a
multi-worker deployment, the effective chat limit scaled with worker count.

## Decision

- Keep the default single-app test behavior unchanged.
- Auto-enable a shared SQLite-backed fixed-window storage backend when
  `WEB_CONCURRENCY > 1` and the FastAPI app exposes `app.state.rate_limit_db_path`.
- Keep the storage local-only by reusing the existing `data/notebooks.db`.
- Create the `rate_limit_counters` table lazily instead of adding a migration.

## Frozen File Override

`core/governance/rate_limit.py` is frozen for normal edits. This task uses a
tight override limited to backend selection, storage wiring, and explicit
multi-worker logging. Existing rate parsing, principal keying, response
payloads, and admin exemption behavior remain unchanged.

## Verification Focus

- Single-app tests still reset chat buckets per app instance.
- Multi-worker app setups share chat buckets across app instances when they use
  the same SQLite database path.
- Main app startup exposes `_DB_PATH` to the limiter so production wiring uses
  the shared backend automatically.
