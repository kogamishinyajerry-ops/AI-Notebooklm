# V4.3 W-V43-5 Codex Retroactive Governance Audit

**Date:** 2026-04-20
**Auditor:** Codex GPT-5.4 self-verification
**Scope:** V4.2 governance PRs #39, #40, #41, and #42
**Task:** W-V43-5
**Decision:** PASS WITH MINOR NOTES

This audit repays the V4.2 governance record debt without rewriting any Claude
Code records. It is intentionally docs-only: no runtime code, tests, migrations,
dependency manifests, citation files, or retrieval files are changed by this
task.

## Source Scope

| PR | Merge commit | Merged at | Scope audited |
|---|---|---:|---|
| [#39](https://github.com/kogamishinyajerry-ops/AI-Notebooklm/pull/39) | `b8de2db` | 2026-04-18 03:45 UTC | V4.2-T1 rate limiting and quotas |
| [#40](https://github.com/kogamishinyajerry-ops/AI-Notebooklm/pull/40) | `225ed1b` | 2026-04-18 03:54 UTC | V4.2-T2 append-only audit log |
| [#41](https://github.com/kogamishinyajerry-ops/AI-Notebooklm/pull/41) | `baa75a7` | 2026-04-18 07:27 UTC | V4.2-T5 SQLite FK enforcement |
| [#42](https://github.com/kogamishinyajerry-ops/AI-Notebooklm/pull/42) | `a8ae8dc` | 2026-04-18 07:58 UTC | V4.2-T3 admin role and dashboard |

Related tracking:

- GitHub issue #44 requests retroactive audit coverage for PR #42.
- Notion Reviews already contain Claude retro-review rows for V4.2 T1/T2/T3/T5.
- Notion now also contains a Codex supplement review for PR #42.
- `docs/architectural_risk_register.md` now tracks `R-2604-02`.

## Findings

No P0 or P1 findings were found in this retroactive pass.

### P2-GOV-001: PR #42 independent-review boundary was not externally verifiable

PR #42 used self-signed external-review wording inside the PR body. The code
delivery appears coherent and heavily tested, but the review provenance in the
PR itself did not preserve the intended Executor != independent reviewer
boundary.

**Impact:** Process integrity debt, not an immediate runtime rollback signal.

**Containment already applied:**

- Codex supplement review created in Notion for PR #42.
- `R-2604-02` recorded in the risk register.
- Future PR bodies must use `Self-verification checklist` wording and must not
  present executor self-review as independent terminal review.
- Historical Claude records are preserved unchanged.

**Required follow-up:** Close GitHub issue #44 through this audit PR once merged.

### P3-GOV-002: V4.2-T3 freeze-pack scope was broader than the shipped API contract

The T3 frozen implementation pack listed a larger admin API surface, including
single-event audit detail and single-principal quota detail endpoints, plus a
different static dashboard path. The shipped PR, operator guide, and tests define
a smaller read-only surface:

- `GET /api/v1/admin/health`
- `GET /api/v1/admin/audit/events`
- `GET /api/v1/admin/quota/usage`
- `GET /admin/ui/`

**Impact:** Traceability drift between planning artifact and shipped contract.
The shipped contract itself is internally consistent and covered by tests, so no
retroactive endpoint backfill is recommended inside W-V43-5.

**Required follow-up:** Treat PR #42 body plus
`docs/admin_role_and_dashboard.md` as the shipped T3 contract. If the omitted
single-resource endpoints are still desired, open a future V4.3 task with a fresh
file plan and tests.

### P3-GOV-003: Older V4.2 PR bodies retain legacy review wording

PR #39, #40, and #41 were merged before the Codex handoff and retain legacy
external-review wording in their bodies. Those bodies are immutable historical
artifacts and should not be edited or reinterpreted.

**Impact:** Historical wording drift only. The associated implementation scopes
have current tests and Notion review rows.

**Required follow-up:** Do not rewrite old PR bodies. Future Codex PRs use the
new self-verification sections required by the 2026-04-20 handoff.

### P3-TECH-004: T1 multi-worker chat throttling remains a known limitation

T1 documents that `chat_requests` uses slowapi `MemoryStore`, so a multi-worker
deployment can multiply the effective chat budget by worker count. Upload and
notebook quotas are SQLite-backed and are not affected by this limitation.

**Impact:** Known deployment limitation for strict multi-worker throttling.

**Required follow-up:** Keep the V4.3 shared-local-store or connection-pool work
item in the backlog. Do not expand W-V43-5 beyond governance audit scope.

## PR-by-PR Audit Notes

### PR #39: V4.2-T1 Rate Limiting and Quotas

**Evidence checked:**

- `docs/RATE_LIMIT_GUIDE.md`
- `tests/test_rate_limit.py`
- `tests/test_quota_admin.py`
- Current historical sentinel runs for T1-related behavior

**Assessment:** The three quota dimensions remain separated: chat request budget,
upload bytes per UTC day, and notebook count. SQLite-backed dimensions persist
across restart, while chat request buckets are explicitly documented as
in-memory.

**Decision:** PASS WITH MINOR NOTES. The only active concern is the documented
multi-worker MemoryStore limitation, tracked as a V4.3 follow-up rather than a
T1 rollback issue.

### PR #40: V4.2-T2 Append-only Audit Log

**Evidence checked:**

- `docs/AUDIT_LOG_GUIDE.md`
- `core/governance/audit_store.py` append and query boundaries
- `core/governance/audit_redact.py` whitelist posture
- `tests/test_audit_log.py`
- `tests/test_audit_query.py`

**Assessment:** The audit table remains append-only via SQLite triggers. Payload
redaction is whitelist-based and excludes raw chat, note, source, studio,
embedding, secret, and citation content. T2 intentionally had no HTTP read API;
the read surface was added later through T3 admin routes.

**Decision:** PASS. No blocking governance finding specific to T2.

### PR #41: V4.2-T5 SQLite FK Enforcement

**Evidence checked:**

- `docs/FK_ENFORCEMENT_GUIDE.md`
- `core/storage/migrations/v4_2_t5_fk_enforcement.py` by reference only
- `tests/test_fk_enforcement.py`
- `tests/test_storage_concurrency.py`

**Assessment:** Notebook-scoped child tables enforce FK semantics through project
SQLite connections. Historical orphan repair is auditable through
`integrity.repair`, and the migration is idempotent through `PRAGMA user_version`.

**Decision:** PASS. No blocking governance finding specific to T5.

### PR #42: V4.2-T3 Admin Role and Dashboard

**Evidence checked:**

- `.planning/v4-2-t3-frozen-pack.md`
- `docs/admin_role_and_dashboard.md`
- `core/governance/admin.py`
- `apps/api/admin_routes.py`
- `tests/test_admin_role.py`
- `tests/test_admin_api.py`
- `tests/test_admin_dashboard.py`
- `tests/test_quota_admin.py`
- `tests/test_rate_limit.py`

**Assessment:** The shipped T3 feature preserves the main security boundaries:
admins are env-allowlisted authenticated principals, not header-promoted users;
admin routes return 503 on missing configuration; successful admin calls emit
`admin.access`; quota bypass does not bypass authentication or audit.

**Decision:** PASS WITH MINOR NOTES. The runtime implementation is acceptable;
the governance record required retroactive Codex supplement coverage.

## C1/C2/C3 Check

| Constraint | Result | Notes |
|---|---|---|
| C1: air-gapped runtime | PASS | W-V43-5 is docs-only. Prior V4.2 features use env, SQLite, stdlib, and pinned existing deps; this task adds no dependency. |
| C2: citation and retrieval guardrail | PASS | W-V43-5 touches no citation XML, gateway, retrieval, or regression baseline files. C2 sentinel remains required in PR verification. |
| C3: branch, PR, self-review, merge discipline | PASS WITH MINOR NOTES | This task exists because PR #42 needed retrospective governance supplementation. Future Codex PRs must keep executor self-verification distinct from independent review. |

## Current Verification Baseline

The current mainline baseline before W-V43-5 implementation was:

```text
python3 -m pytest -q
395 passed

python3 -m pytest -q tests/test_retrieval_quality_regression.py
8 passed
```

The W-V43-5 PR must rerun full pytest, the C2 sentinel, and historical sentinel
families before merge even though it is docs-only.

## Decision

W-V43-5 is fit to merge if its PR completes the required self-verification and
Notion review record. It should close GitHub issue #44, retain all historical
Claude Code records unchanged, and let V4.3 proceed to heavier technical tasks
only after this governance debt is recorded.
