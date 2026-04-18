# Admin Role & Dashboard (V4.2-T3)

Operator guide for the admin role and the `/admin/ui/` dashboard introduced in V4.2-T3.

## Configuring admins

Admin identity is sourced **only** from the `NOTEBOOKLM_ADMIN_PRINCIPALS` environment
variable — a comma-separated list of `principal_id` values that must already appear
in `NOTEBOOKLM_API_KEYS`. There is no header claim, JWT, or separate admin key.

```bash
# every admin must already exist in NOTEBOOKLM_API_KEYS
export NOTEBOOKLM_API_KEYS="alice:key-alice,bob:key-bob,root:key-root"
# this promotes alice + root (bob stays a regular user)
export NOTEBOOKLM_ADMIN_PRINCIPALS="alice,root"
```

Rules:

- **empty or unset** → zero admins. Admin endpoints return **503** (not 403) so the
  operator gets a loud signal that the allowlist is misconfigured rather than a
  silent lockout.
- **whitespace-only** → treated as empty.
- **entries with internal whitespace** (e.g. `"bob bob"`) are skipped with a
  `comac.governance.admin` WARNING log. Trailing commas and duplicates are tolerated.
- **admin never bypasses authentication** — it's a strict extension, not a
  replacement. An admin without a valid API key still gets 401.

## What admin bypasses

Admin principals skip quota/rate-limit dimensions but still have their activity
recorded for observability:

| Dimension                     | Admin behavior                                             |
|-------------------------------|------------------------------------------------------------|
| Chat rate limit (slowapi)     | Bypassed via `exempt_when=is_admin_exempt`                 |
| Daily upload bytes cap        | Bypassed; **bytes still recorded** in `daily_upload_usage` |
| Notebook count cap            | Bypassed                                                   |
| Authentication                | **Not** bypassed (always required)                         |
| Append-only audit             | Every admin endpoint call emits `admin.access`             |

## Endpoints

All under `/api/v1/admin/*`, gated by `Depends(require_admin)`.

| Method | Path                            | Purpose                                              |
|--------|---------------------------------|------------------------------------------------------|
| GET    | `/api/v1/admin/health`          | Liveness + auth_enabled + admin_count + caller       |
| GET    | `/api/v1/admin/audit/events`    | Cursor-paginated audit log                           |
| GET    | `/api/v1/admin/quota/usage`     | Per-principal uploads + notebook counts              |
| GET    | `/admin/ui/`                    | Static HTML dashboard (no server auth; API gates it) |

### Response ladder for admin routes

- **200** — authenticated admin; `admin.access` audit row emitted.
- **401** — missing or invalid `x-api-key` / `Authorization: Bearer`. No audit.
- **403** — authenticated but `principal_id` not in the allowlist. No audit.
- **503** — `NOTEBOOKLM_API_KEYS` unset, or `NOTEBOOKLM_ADMIN_PRINCIPALS` empty.
  Signals a config problem rather than denial.
- **400** — invalid cursor in `/audit/events?cursor=…`.
- **422** — `limit` outside `[1, 200]`.

### `/audit/events` query params

`event`, `principal_id`, `outcome`, `from_ts` (>=), `to_ts` (<), `limit` (1–200,
default 50), `cursor` (opaque base64 JSON). All optional; all filters AND together.

The cursor is produced server-side from `(ts_utc, event_id)` — treat it as opaque.
Order is `ts_utc DESC, event_id DESC` (stable tiebreaker within the same second).

## `admin.access` audit event

Every 200 response from an admin route appends one row:

```
event=admin.access
outcome=success
resource_type=admin.endpoint
resource_id=/api/v1/admin/<route>
http_status=200
payload_json={"admin.method": ..., "admin.path": ..., "admin.query": {...}}
```

The redaction whitelist (`core/governance/audit_redact.py`) allows `admin.method`,
`admin.path`, and `admin.query` through — other payload fields are dropped per the
T2 redaction rules.

## Dashboard (`/admin/ui/`)

Single-file vanilla HTML (~190 lines). Enter your admin API key, press **Refresh**.
The key is stored in `localStorage` under `comac_admin_api_key`. The dashboard
does no client-side authz — every 401/403 from the backend surfaces as an error
banner.

Features:

- Health card: status, uptime, admin_count, caller identity.
- Quota table: per-principal bytes_used, daily_limit, notebook_count, notebook_max.
- Audit table: filters (event, principal_id, outcome), cursor-paginated.

## Ops runbook

**Adding an admin live** — no restart needed; `get_admin_principal_ids()` re-reads
the env on every call. Update your secrets manager / systemd override, then:

```bash
systemctl show comac-notebooklm -p Environment | grep NOTEBOOKLM_ADMIN_PRINCIPALS
```

**Removing an admin** — same. The next request from that principal will see
`is_admin=False` and fall back to regular quotas.

**All admins locked out** — if `NOTEBOOKLM_API_KEYS` is set but
`NOTEBOOKLM_ADMIN_PRINCIPALS` is unset/blank, every admin endpoint returns 503
(not 403), which is the intended signal. Repair the env and reload.

**Verifying admin is working**:

```bash
curl -H "x-api-key: $ADMIN_KEY" http://localhost:8000/api/v1/admin/health
# → 200 with status=ok, admin_count=<n>, caller.is_admin=true
```

## Design boundaries (frozen pack FD-1 / FD-9 / FD-10)

- env-only allowlist (C1 zero-new-dep — no JWT library, no OAuth client)
- binary `is_admin` (no role hierarchy in T3)
- admins are a strict subset of authenticated principals
- admin.access audit rows are append-only (T2 triggers still apply)
- the dashboard ships read-only; write operations remain on the normal routes,
  which admins can still call with quota bypass
