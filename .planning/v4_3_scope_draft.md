# V4.3 Scope Draft

**Status:** Draft — pending Kogami authorization
**Author:** Claude Code Opus 4.7 (Extended Autonomy v1.3)
**Date:** 2026-04-18
**Depends on:** `main` @ `7fd8877` (V4.2 closed)

This document is a planning-only draft. It proposes what V4.3 should cover, reconciles
two open Notion anomalies from V4.0/V4.1, and enumerates frozen-file invariants the
phase must respect. No code change is implied by merging this doc.

---

## 1. Open Notion anomalies (to resolve before V4.3 starts)

### 1.1 V4.1b orphan pointer

- **Source:** V4.1 (`56bb9c1b-5939-4371-9109-9535c2413799`) has
  `Next Phase Pointer = "V4.1b: Prometheus /metrics + Should-item cleanup → V4.2"`.
- **Reality:** No V4.1b Phase row ever existed. V4.2 (Multi-User Governance) was
  started directly after V4.1. V4.1b work never landed on `main`.
- **Proposed disposition:** **Absorb V4.1b into V4.3** as two explicit work items:
  - W-V43-1: `/metrics` Prometheus surface (gated behind ENV flag; no network exposure by default to honor C1).
  - W-V43-2: Close the V4.1 "Should" checklist (concrete list to be enumerated in the V4.3 freeze pack).
- **Alternative considered:** File V4.1b separately. **Rejected** because:
  - No unique gate scope remains — both items are cross-cutting tech debt.
  - A separate phase would require its own freeze pack, reviewer, and merge cadence.
- **Historical record policy:** V4.1's `Next Phase Pointer` is kept as-is (immutable
  historical value). V4.3 freeze pack will back-link to it.

### 1.2 V4.0 stale status

- **Source:** V4.0 (`f9e897a7-d888-4c1f-ae32-ad8d68830685`) has
  `Status = "Executing"` and `Review Decision = "Conditional Pass"` even though its
  branch (`codex/v4-0-eval-and-deployment-pack`) has not progressed in weeks and
  V4.1/V4.2 already merged downstream.
- **Proposed disposition:** Leave as-is. V4.0's terminal state is a Kogami decision,
  not an Executor reconciliation. Flagged here as a known Notion↔reality drift.
- **Recommendation for Kogami:** close V4.0 as either `Completed` (if its conditional
  pass was accepted) or `Cancelled` (if superseded). Do not let Executor mutate the
  `Review Decision` field — that would be a §4 prohibited historical-record edit.

---

## 2. V4.3 proposed scope

**Working name:** V4.3 — Observability, Tech-Debt Cleanup & Test-Isolation Fix

### 2.1 In-scope work items

| ID | Item | Origin | Priority |
|---|---|---|---|
| W-V43-1 | `/metrics` Prometheus surface (env-gated, loopback-only by default) | V4.1b pointer | P1 |
| W-V43-2 | Close V4.1 "Should" checklist | V4.1b pointer | P2 |
| W-V43-3 | Root-cause + fix R-2604-01 test-isolation fragility | `docs/architectural_risk_register.md` | P1 |
| W-V43-4 | Widen `Reviews` DB `Reviewer Model` enum to include `Opus 4.7` | Extended Autonomy v1.3 drift | P2 |
| W-V43-5 | Retroactive Opus 4.7 audit of V4.2 T1/T2/T3/T5 (closes GitHub Issue #44) | Autonomy contract §6 | P1 |

### 2.2 Explicitly out of scope

- Any change to `auth.py`, `rate_limit.py`, `quota_store.py`, `audit_store.py`,
  `audit_logger.py`, V4.2-T5 migration, T1/T2/T4/T5 test files, or the citation/
  retrieval pipeline. These are FROZEN under v1.3 §3.
- Any change to the C2 retrieval sentinel thresholds or fixtures.
- New external dependencies. C1 forbids it.

### 2.3 Entry criteria

- [ ] V4.3 Phase row created in Notion (`Draft` / `Pending`).
- [ ] V4.3 freeze pack drafted at `docs/v4_3_freeze_pack.md`.
- [ ] Kogami signs off on the disposition of the V4.0 and V4.1b anomalies.

### 2.4 Exit criteria

- [ ] W-V43-3 closed: R-2604-01 root-caused; subset + full-suite both green under any ordering.
- [ ] W-V43-1 merged with full-suite + C2 sentinel green.
- [ ] W-V43-5 evidenced: Opus 4.7 audit attached to each of T1/T2/T3/T5 review rows.
- [ ] V4.1 `Next Phase Pointer` back-linked from V4.3 freeze pack.

---

## 3. Autonomy & gate posture

Under Extended Autonomy v1.3, V4.3 continues with Executor-does-Self-Review. The
**5-PR deep-review ceiling** (§6 D) applies: after 5 autonomous merges since the last
Kogami deep review, Executor must stop and request one.

Current PR counter since Extended Autonomy v1.3 start: **2** (PR #43, PR #45) plus this one
would make **3**. Two PRs of headroom remain before a mandatory Kogami deep-review request.

---

## 4. This doc is not a commitment

Merging this doc does not start V4.3. It only records the proposed scope and open
anomalies so Kogami can authorize — or redirect — before any V4.3 code lands.
