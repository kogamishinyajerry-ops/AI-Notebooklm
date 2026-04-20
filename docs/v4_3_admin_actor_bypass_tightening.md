# V4.3 W-V43-8: Admin Actor Bypass Tightening

## Problem

V4.2 introduced admin identity as a strict extension of authentication, but the
runtime hook in `apps/api/main.py` still marked any admin principal as eligible
for the chat rate-limit bypass on ordinary user-facing routes. That made the
effective policy broader than the actual admin surface, which is read-only and
currently limited to `/api/v1/admin/*`.

## Decision

- Keep the V4.2 store-level `is_admin` APIs and tests unchanged.
- Tighten main-app runtime behavior so admin bypass is enabled only for explicit
  admin-route requests.
- Leave normal user-facing routes, including `/api/v1/chat`, subject to the
  same rate limits as other authenticated principals.

## Why This Is Safe

- Authentication remains unchanged; admin is still resolved from
  `NOTEBOOKLM_ADMIN_PRINCIPALS`.
- Read-only admin endpoints continue to work and still identify the caller as an
  admin.
- The change is scoped to `apps/api/main.py` request wiring, so it does not
  mutate the frozen V4.2 quota-store contracts or the legacy migration CLI.

## Verification Focus

- Main-app admin identity no longer bypasses chat throttling.
- `/api/v1/admin/health` still recognizes an authenticated admin principal.
- Existing V4.2 T3 helper-level admin bypass assertions remain untouched.
