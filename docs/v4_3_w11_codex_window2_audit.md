# V4.3 W-V43-11 Retrospective Codex Audit of Window 2

**Date:** 2026-04-26 Asia/Shanghai
**Author / orchestrator:** Claude Code (Opus 4.7, 1M context) — Executor self-verification
**Codex auditor:** Codex GPT-5.4 v0.118.0 (research preview)
**Audit target:** Three Window-2 PRs that triggered the CLAUDE.md "必须调用 Codex" rule but merged without independent Codex review
**Risk class addressed:** R-2604-03 (logged in `docs/v4_3_window_2_reconciliation.md` §5)

> **Governance note.** This is a Self-verification artifact (W-V43-11 / Window-3 PR 2). Codex acted as an independent retrospective reviewer; Claude Code did not edit Codex's findings, only collected them and added executor-side reading notes. Per V4.3 handover §C3, this PR body must use Self-verification wording and must not be presented as a Gate Review.

---

## 1. Why this audit exists

`docs/v4_3_window_2_reconciliation.md` (W-V43-10, merged 2026-04-26 as commit `e3aa010`) logged R-2604-03 — three Window-2 PRs (#53, #54, #55) merged without the Codex review their CLAUDE.md trigger required. PR #56 was correctly reviewed by `chatgpt-codex-connector`; the others were not. This document repays the Codex-coverage debt without rewriting any merged PR body or Notion review row.

| PR | Trigger | Codex review at merge? | This audit's verdict |
|---|---|---|---|
| #55 | multi-frontend + UI flow change | None | **CHANGES_REQUIRED** (2 HIGH, 3 MED, 1 LOW — see §2) |
| #54 | adapter boundary (borderline) | None | **APPROVE WITH FOLLOW-UPS** (1 LOW — see §3) |
| #53 | adapter boundary | None | **APPROVE WITH FOLLOW-UPS** (2 MED, 1 LOW — see §4) |

The full Codex finding documents are preserved at:
- `/tmp/codex_w11_pr55_findings.md` (89 lines)
- `/tmp/codex_w11_pr54_findings.md` (312 lines)
- `/tmp/codex_w11_pr53_findings.md` (324 lines)

This document inlines their severity tables and the executor's reading notes; the full text remains in /tmp for future reference and is not committed (audit output, not a runtime artifact).

---

## 2. PR #55 — `feat(v4.3): package demo usability candidate`

**Codex verdict: CHANGES_REQUIRED.** PR #55 is mostly clean on dependency creep and the new Obsidian filesystem integration is stdlib-only. But the audit surfaced two **HIGH-severity** findings that affect runtime correctness, plus three medium and one low.

### 2.1 Severity-classified findings (Codex output, verbatim severity column)

| ID | Sev | Title | File:line | Recommendation |
|---|---|---|---|---|
| W-V43-11-01 | **High** | `is_fully_verified` is advisory; raw evidence and unverified answers still reach the UI | `apps/api/main.py:1197-1270`; `apps/web/static/js/app.js:1260-1319` | Suppress or heavily downgrade assistant answers/evidence when `is_fully_verified=false`, or split raw retrieval evidence into a separately-named non-answer surface with explicit UI quarantine. |
| W-V43-11-02 | **High** | Demo-seeded synthetic content can escape through unscoped `/api/v1/chat` calls | `apps/api/main.py:305-316`, `1127-1164`; `core/retrieval/retriever.py:113-154` | Make `notebook_id` mandatory on `/api/v1/chat` (and reject missing legacy aliases), or apply a deny-by-default filter when no notebook scope is present. |
| W-V43-11-03 | Medium | Provider choice is not preserved in the audit trail | `apps/api/main.py:1071-1080`, `1119-1123`, `1271-1278`; `core/governance/audit_logger.py:112-154` | Add `llm_provider`, `llm_configured_url`, `is_external_validation` to audit payloads for chat / studio / health operations. |
| W-V43-11-04 | Medium | MiniMax lane exfiltrates retrieved notebook context by design | `core/governance/prompts.py:82-91`; `apps/api/main.py:1197-1204`, `1812-1821`; `core/llm/vllm_client.py:212-234`, `367-382` | Treat `minimax` as an explicit external-processing mode in UI / docs / runtime logs. Add operator-visible confirmation or policy flag before allowing notebook content to leave the machine. |
| W-V43-11-05 | Medium | "Local" provider is not loopback-only (accepts RFC1918 / `*.local` / `*.internal` / Docker-bridge hosts) | `core/llm/vllm_client.py:74-90`, `123-156`, `159-169`, `302-309`, `384-395` | If air-gap policy means same-host only, restrict `local` to loopback and move private-LAN hosts behind a separate, explicitly-named provider or override. |
| W-V43-11-06 | Low | Client blindly opens server-returned Obsidian URLs | `apps/web/static/js/app.js:1527-1538`, `1721-1732`, `1916-1925` | Scheme-allowlist `obsidian://` on the client before calling `openExternal()`; reject or toast unexpected URLs. |

### 2.2 Independent executor reading (subset — for findings where Claude Code also read the code)

Claude Code independently read `core/integrations/obsidian_export.py` (full 271 lines), `core/llm/vllm_client.py` (full 397 lines), and the `core/retrieval/vector_store.py` bbox round-trip diff. Independent findings:

- **`obsidian_export.py`:** Confirmed PASS — stdlib-only, no network, path sanitization replaces all OS path separator chars (`\/:*?"<>|`) with `-`, no traversal vector. Minor robustness note: long citation `content` produces wide YAML frontmatter lines (formatting, not a defect).
- **`vllm_client.py`:** Confirmed Codex's W-V43-11-05 (private-LAN whitelist beyond loopback). Independently noted that `host.docker.internal` whitelist could route differently in misconfigured Docker networks — same family of concern. Confirmed `LLMConfig.to_dict()` strips `api_key` (line 47-50) so health/audit payloads cannot leak credentials.
- **`vector_store.py` bbox:** Confirmed Codex's PASS on round-trip correctness. Independently noted a minor robustness gap in `_deserialize_metadata`: when `bbox` is present as a corrupt JSON string, the code silently leaves the corrupt string in place (`if isinstance(parsed, list)` is the only update gate; non-list `parsed` doesn't trigger fallback to `None`). Filed as informational under W-V43-11-06 family.

### 2.3 Recommended remediation PRs

| Remediation work item | Severity | UI gate triggered? | Codex required for the fix PR? |
|---|---|---|---|
| W-V43-11.1 Fix `is_fully_verified` to act as a real gate (or quarantine raw evidence under a non-answer surface) | High | **YES** — affects user-visible chat response | YES (multi-frontend + API contract) |
| W-V43-11.2 Make `notebook_id` mandatory on `/api/v1/chat`; deny-by-default if absent | High | borderline (existing UI always sends; only legacy callers affected) | YES (API contract change) |
| W-V43-11.3 Add `llm_provider` + `llm_configured_url` + `is_external_validation` to chat / studio / health audit payloads | Medium | NO | YES (audit contract) |
| W-V43-11.4 Operator-visible flag / startup-banner / health-status field when `LLM_PROVIDER=minimax` is active | Medium | YES (status surface visible in UI) | YES |
| W-V43-11.5 Restrict `LLM_PROVIDER=local` to loopback only; move private-LAN behind a separately-named provider | Medium | NO | YES (governance/adapter boundary) |
| W-V43-11.6 Client-side scheme allowlist for `obsidian://` URLs before `openExternal()` | Low | YES (frontend change) | YES (multi-frontend if combined with other UI) |

---

## 3. PR #54 — `fix: tighten admin actor bypass`

**Codex verdict: APPROVE WITH FOLLOW-UPS.** The PR fixes the shipped issue: an authenticated admin principal is no longer exempt from chat throttling. The narrowed behavior is correctly implemented at `apps/api/main.py:332-351` (`_admin_runtime_bypass_enabled` returns `True` only when `request.url.path.startswith("/api/v1/admin/")`), and the regression test at `tests/test_rate_limit.py:680-707` exercises the exact path-scoping scenario.

Codex independently re-ran targeted pytest slices in an isolated `/tmp` venv:
- `tests/test_rate_limit.py` (slice): 4 passed
- `tests/test_admin_api.py` (slice): 4 passed
- `tests/test_admin_role.py` (slice): 4 passed

### 3.1 Severity-classified findings (Codex output, verbatim)

| ID | Sev | Title | File:line | Recommendation |
|---|---|---|---|---|
| PR54-1 | Low | Path-scoping contract is split across auth wiring and admin dependency | `core/governance/admin.py:148-152` | Remove the unconditional `mark_admin_request(True)` from `require_admin()`, or gate it with the same `/api/v1/admin/` predicate used by `apps/api/main.py:332-351` so the invariant is single-sourced. |

### 3.2 Recommended remediation

Treat as Low-priority hardening. Single-sourcing is a code-quality win, not a runtime correctness fix. Could be combined with W-V43-11.3 (audit-payload work) into a small "governance plumbing" PR.

---

## 4. PR #53 — `[codex] W-V43-7 multi-worker chat rate-limit correctness`

**Codex verdict: APPROVE WITH FOLLOW-UPS.** The SQLite increment path is correctly serialized via `BEGIN IMMEDIATE` + read-after-lock + atomic write — Codex traced this through `core/governance/sqlite_rate_limit_storage.py:60-104` and confirmed two workers cannot collide on a read-modify-write window. The fix is technically sound. The follow-ups are around deployment hardening and concurrent-worker test coverage, not the increment logic itself.

(Codex's first audit attempt exited 144 due to account quota; retry succeeded after `cx-auto 20` switched to `picassoer651@gmail.com` at 48% score. Codex flagged that it could not rerun the committed pytest targets in its sandbox because `slowapi` and `limits` are not installed in the codex CLI's venv. Claude Code's local pytest run on `origin/main` HEAD reported `tests/test_rate_limit.py: 21 passed` and `tests/test_sqlite_rate_limit_storage.py` cases passed in W-V43-10 §6 baseline.)

### 4.1 Severity-classified findings (Codex output, verbatim)

| ID | Sev | Title | File:line | Recommendation |
|---|---|---|---|---|
| RL-53-01 | Medium | Backend choice still depends on env/state wiring; a misconfigured multi-worker process can silently keep `MemoryStorage` | `core/governance/rate_limit.py:107-132` | Add a deployment check or startup assertion for multi-worker mode so the SQLite backend cannot be silently bypassed. |
| RL-53-02 | Medium | Merged tests do not prove concurrent worker correctness | `tests/test_rate_limit.py:358-394` | Add a committed concurrent-writer regression test (process-based) that contends on the same SQLite file and asserts exact final counts. |
| RL-53-03 | Low | Pooled-connection shutdown cleanup is not wired into the app lifecycle | `core/storage/sqlite_db.py:151-157` | Register a FastAPI shutdown hook that calls `close_connection_pools()` when pooled SQLite connections are enabled. |

### 4.2 Independent executor reading

Claude Code did not separately read `core/governance/sqlite_rate_limit_storage.py` line by line during this audit. Trusting Codex's `BEGIN IMMEDIATE` analysis combined with the merged test suite green status (PR #53's verification reported `21 passed` on `tests/test_rate_limit.py` plus separate cases for `test_sqlite_rate_limit_storage.py`) is the operative correctness signal here. RL-53-02's recommendation (committed concurrent-worker test) is a real test-coverage gap and is the most actionable follow-up.

### 4.3 Recommended remediation PRs

| Remediation work item | Severity | UI gate triggered? | Codex required for fix PR? |
|---|---|---|---|
| W-V43-11.7 Add startup assertion when `WEB_CONCURRENCY > 1` ensuring SQLite backend is wired (closes RL-53-01) | Medium | No | Yes (governance/adapter boundary) |
| W-V43-11.8 Add process-based concurrent-writer test for SQLite rate-limit storage (closes RL-53-02) | Medium | No | Borderline (test infra) |
| W-V43-11.9 Wire `close_connection_pools()` into FastAPI shutdown hook (closes RL-53-03) | Low | No | No (small infra change) |

W-V43-11.7 and W-V43-11.8 can land together as a small "rate-limit hardening" PR. W-V43-11.9 can be combined with W-V43-12 (cold-cache fail-fast guard from W-V43-10's Window-3 sequencing).

---

## 5. Remediation roadmap

| ID | Origin | Severity | UI gate? | Suggested Window-3 slot |
|---|---|---|---|---|
| W-V43-11.1 | PR #55 finding W-V43-11-01 | High | Yes | Stop for UI verification before merge — handover priority 1 |
| W-V43-11.2 | PR #55 finding W-V43-11-02 | High | Borderline | Window-3 next code PR |
| W-V43-11.3 | PR #55 finding W-V43-11-03 + PR54-1 (combined) | Medium + Low | No | Window-3 governance plumbing PR |
| W-V43-11.4 | PR #55 finding W-V43-11-04 | Medium | Yes (status surface) | Stop for UI verification |
| W-V43-11.5 | PR #55 finding W-V43-11-05 | Medium | No | Window-3 governance PR |
| W-V43-11.6 | PR #55 finding W-V43-11-06 | Low | Yes (frontend) | Combined with W-V43-11.1/.4 |
| W-V43-11.7 | PR #53 finding RL-53-01 | Medium | No | Combined with .8 — rate-limit hardening |
| W-V43-11.8 | PR #53 finding RL-53-02 | Medium | No | Combined with .7 |
| W-V43-11.9 | PR #53 finding RL-53-03 | Low | No | Combined with W-V43-12 (cold-cache guard) |

The two HIGH findings (W-V43-11-01, W-V43-11-02) gate the security posture of `/api/v1/chat`. They are not regressions Window 2 introduced — the unscoped chat path predates Window 2, and the `is_fully_verified` advisory mode was already the design before PR #55. PR #55 made the gap easier to exploit (added unverified evidence rendering), but did not invent it.

---

## 6. R-2604-03 disposition

R-2604-03 (Window-2 Codex review coverage gap) was logged in `docs/v4_3_window_2_reconciliation.md` §5 as Open. With this audit's findings landed:

- **Status proposed:** Move to **Mitigated** — Codex independent review now covers PRs #55 and #54 (and #53 once the running audit completes).
- **Remediation tail:** The HIGH findings on PR #55 (W-V43-11-01, W-V43-11-02) become first-class Window-3 work items, not part of R-2604-03.
- **Process correction:** Future Window-3 PRs that match CLAUDE.md "必须调用 Codex" triggers must wait for `chatgpt-codex-connector` review before merge. Self-verification alone is insufficient for those categories.

---

## 7. What this audit did NOT verify

- **Live network capture for the MiniMax lane.** Codex inferred off-box payload contents from code inspection plus PR #55's own tests; no packet capture was performed. If the air-gap policy needs runtime proof, a separate W-V43-11.7 task should run an end-to-end smoke against a sandboxed MiniMax mock to confirm payload boundaries.
- **End-to-end runtime exercise of `ab695c4`.** Both audits read the merged-snapshot code and ran targeted pytest slices, but did not reproduce the merge gate's full-suite verification.
- **Notion Reviews DB cross-check.** This document does not query Notion to confirm whether retro Codex review rows exist for #53 / #54 / #55. That is a manual operator step (or a future automation work item).

---

## 8. Self-verification (this PR)

| Check | Result |
|---|---|
| C1 — no new Python dependencies | ✅ docs-only |
| C2 — citation/retrieval guardrail | ✅ no citation/retrieval files touched in this PR's diff |
| C3 — branch + PR + self-review wording | ✅ branch `feat/v4-3-w11-codex-retro-audit`; PR body uses Self-verification template; no "Gate Review" wording |
| Frozen file list | ✅ no overlap |
| `tests/` modifications | ✅ none |
| `requirements.txt` modifications | ✅ none |
| Notion Reviews DB row | to be created post-merge per §C3 |

**Decision:** Self-Verified. This PR is the W-V43-11 retro audit deliverable; it documents but does not implement the remediation work items.

**Signed:** Claude Code (Opus 4.7, 1M context) — orchestrator
**Codex contributions:** PR #55 audit (CHANGES_REQUIRED, 6 findings) + PR #54 audit (APPROVE WITH FOLLOW-UPS, 1 finding) + PR #53 audit (APPROVE WITH FOLLOW-UPS, 3 findings).

Total: **10 Codex-identified follow-up items** across the three PRs. None require immediate runtime rollback (Window-2 PRs are not regressions; the gaps were pre-existing or design-level). The two HIGH findings on PR #55 (W-V43-11-01 advisory verification, W-V43-11-02 unscoped chat) gate next-PR priority and require UI verification.
