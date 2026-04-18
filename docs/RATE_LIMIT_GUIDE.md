# Rate Limiting & Quota Guide

V4.2-T1 adds three independent governance controls at the FastAPI layer.

## What Is Enforced

| Dimension | Default | Scope | Storage |
| --- | --- | --- | --- |
| `chat_requests` | `30/minute` | per principal | slowapi `MemoryStore` |
| `upload_bytes` | `524288000` bytes/day | per principal | SQLite `daily_upload_usage` |
| `notebook_count` | `50` notebooks | per principal | realtime `COUNT(*)` from `notebooks` |

These dimensions do not share state.

- A user hitting the chat request budget does not consume upload quota.
- A large upload does not affect notebook creation.
- Notebook cap is computed from persisted notebook ownership, not a side table.

## Response Format

Any enforced limit returns:

```json
{
  "detail": "Rate limit exceeded: <dimension>",
  "retry_after": 60
}
```

The response also includes:

```text
Retry-After: 60
```

Known dimensions:

- `chat_requests`
- `upload_bytes`
- `notebook_count`

## Configuration

All configuration uses single-purpose environment variables.

```bash
NOTEBOOKLM_CHAT_RATE=30/minute
NOTEBOOKLM_UPLOAD_DAILY_BYTES=524288000
NOTEBOOKLM_NOTEBOOK_MAX=50
```

Examples:

```bash
NOTEBOOKLM_CHAT_RATE=10/minute
NOTEBOOKLM_UPLOAD_DAILY_BYTES=1073741824
NOTEBOOKLM_NOTEBOOK_MAX=100
```

Notes:

- `NOTEBOOKLM_CHAT_RATE` must match `N/unit`.
- Supported units are `second`, `minute`, `hour`, and `day`.
- Invalid values fall back to defaults and emit a warning at startup.
- Numeric quota env vars must be positive integers.

## Runtime Behavior

### Chat Request Limiting

- Implemented with `slowapi`.
- Key function uses `principal.principal_id`, never the raw API key.
- When auth is disabled, the limiter falls back to client IP.

### Daily Upload Quota

- Stored in SQLite table `daily_upload_usage`.
- Usage is recorded with an UPSERT-based atomic increment.
- Quota survives process restarts because the state is persisted in SQLite.
- Usage resets automatically when the UTC date changes.

### Notebook Count Cap

- No separate quota table is used.
- The cap checks `SELECT COUNT(*) FROM notebooks WHERE owner_id = ?`.
- Notebook creation is serialized inside a SQLite write transaction to avoid concurrent cap bypass.
- Deleting a notebook immediately reduces the counted total.

## Multi-Worker Limitation

`chat_requests` uses in-memory state.

If `WEB_CONCURRENCY > 1`:

- each worker maintains its own chat rate buckets
- the effective chat budget is approximately multiplied by worker count
- upload and notebook quotas are not affected because they use SQLite-backed state

At startup the API emits:

- a warning log containing `rate_limit.multi_worker_warning`
- a structured JSON log with worker count metadata

Current recommendation:

- accept this limitation for low-concurrency internal deployments
- keep worker count low if strict chat throttling is required

## Troubleshooting

### Chat limit does not trigger when running multiple workers

Expected with `MemoryStore`.

Check:

- `WEB_CONCURRENCY`
- startup logs for `rate_limit.multi_worker_warning`

### Upload quota appears to survive restart

Expected.

Check SQLite directly:

```sql
SELECT principal_id, usage_date, bytes_used, updated_at
FROM daily_upload_usage
ORDER BY updated_at DESC;
```

### Notebook creation returns 429 unexpectedly

Inspect notebook ownership counts:

```sql
SELECT owner_id, COUNT(*) AS notebook_count
FROM notebooks
GROUP BY owner_id
ORDER BY notebook_count DESC;
```

### Invalid env override is ignored

Expected behavior is fallback plus warning.

Check logs for:

- `NOTEBOOKLM_CHAT_RATE=... is invalid; falling back`
- positive integer fallback warnings for upload or notebook caps

## C1 Notes

- `slowapi` and `limits` are pure Python in-process dependencies.
- This implementation is validated against `slowapi==0.1.9` and `limits==4.2`.
- No external quota service is required.
- No telemetry or network I/O is introduced by this feature.

## V4.3 Follow-Up

Tracked follow-up items for the next governance round:

- replace `MemoryStore` with a shared local store for true multi-worker chat throttling
- add retention cleanup for stale `daily_upload_usage` rows
- extend quota bypass semantics for admin principals in V4.2-T3
