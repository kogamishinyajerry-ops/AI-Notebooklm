# Audit Log Guide

V4.2-T2 adds an append-only audit log for governance-sensitive write paths.

## What Is Logged

The audit subsystem records these event names:

- `space.create`
- `notebook.create`
- `notebook.delete`
- `source.upload`
- `source.delete`
- `chat.request`
- `chat.history.clear`
- `note.create`
- `note.update`
- `note.delete`
- `studio.create`
- `studio.delete`
- `graph.generate`
- `quota.denied`
- `auth.denied`

`GET` routes, health checks, static assets, retrieval internals, and metrics reads are out of scope.

## Storage Model

Primary storage is SQLite table `audit_events` in the main application database.

The table is append-only:

- `audit_events_no_update` aborts any `UPDATE`
- `audit_events_no_delete` aborts any `DELETE`

Indexed access paths:

- `idx_audit_ts`
- `idx_audit_principal_ts`
- `idx_audit_event_ts`
- `idx_audit_resource`

There is no HTTP read API in V4.2-T2. Read-side access is deferred to V4.2-T3.

## Record Shape

Each row stores:

- `event_id`
- `ts_utc`
- `event`
- `outcome`
- `actor_type`
- `principal_id`
- `request_id`
- `remote_addr`
- `resource_type`
- `resource_id`
- `parent_resource_id`
- `http_status`
- `error_code`
- `payload_json`
- `schema_version`

`actor_type` is one of:

- `user`
- `anonymous`
- `system`

When auth is disabled, audit identity falls back to `ip:<remote_addr>`.

## Payload Redaction

`payload_json` is whitelist-based and capped at 2048 bytes.

Allowed business fields:

- `title`
- `space_id`
- `notebook_id`
- `source_id`
- `note_id`
- `source_type`
- `content_type`
- `bytes_size`
- `filename_sha256`
- `ua_sha256`
- `chat.message_length`
- `chat.history_turns`
- `quota.dimension`
- `quota.limit`
- `quota.used`

Redaction rules:

- raw filenames are never stored; only `filename_sha256` (first 16 hex chars)
- raw user agent strings are never stored; only `ua_sha256` (first 16 hex chars)
- chat bodies, note content, studio content, file content, secrets, headers, embeddings, and citation XML are never stored
- string field values are truncated to 256 characters
- oversized payloads are reduced and marked with `"_truncated": true`

## JSON Mirror

Each successful append is also mirrored through `emit_json_log(...)`.

The JSON log envelope uses:

- `event: "audit"`

Because `event` is already used by the logging envelope, the stored audit event name is mirrored as:

- `audit_event`

If SQLite append fails, the request still proceeds and the logger emits:

- `event: "audit_append_failed"`
- a fallback `event: "audit"` mirror line

## Operational Checks

Inspect recent rows:

```bash
python3 scripts/audit_tail.py --last 20
```

Inspect recent rows from a custom DB path:

```bash
python3 scripts/audit_tail.py --db /path/to/notebooks.db --last 50
```

## Manual Retention

V4.2-T2 does not prune automatically.

Manual prune workflow:

```bash
python3 scripts/audit_prune.py --before 2026-01-01 --confirm
```

The prune script temporarily drops the append-only triggers, deletes old rows inside a write transaction, then recreates the triggers before commit.

## Troubleshooting

### A write succeeded but no audit row appeared

Check application logs for:

- `event="audit_append_failed"`

The request path is designed not to fail closed on audit SQLite errors.

### Audit payload contains less data than expected

Expected with whitelist redaction.

Only approved metadata survives into `payload_json`.

### No `/audit` endpoint exists

Expected.

V4.2-T2 is write-only by design. Admin read paths are reserved for V4.2-T3.

## Compliance Notes

- C1: SQLite and stdlib logging only; no new network dependency or telemetry
- C2: citation XML and chat answer bodies are intentionally excluded from audit payloads
- C3: ship through feature branch and PR review only
