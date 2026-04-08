# Phase 5 Implementation Notes

**Document ID:** APLH-IMPL-P5
**Version:** 1.0.0 (Phase 5 complete)
**Date:** 2026-04-06
**Status:** Phase 5 Implemented — Accepted by `docs/PHASE5_REVIEW_REPORT.md` on 2026-04-07

---

## Phase 5: Controlled Actual Promotion into Formal Baseline

**Status:** Implemented — Accepted (v1.0.0, accepted on 2026-04-07)

### New Files

| File | Type | Purpose |
|------|------|---------|
| `services/promotion_manifest_manager.py` | NEW | Manages lifecycle states (pending, promoted, expired) of manifest files (P5-1). |
| `services/promotion_guardrail.py` | NEW | Strictly enforces target path boundaries to `/artifacts/{modes,transitions,guards}` (Gate P5-B). |
| `services/promotion_executor.py` | NEW | Executes physical file copying from Demo to Formal safely and atomically (P5-2). |
| `services/promotion_audit_logger.py` | NEW | Creates immutable ledger entry per execution into `.aplh/formal_promotions_log.yaml`. |
| `services/formal_population_checker.py` | NEW | Runs static checking automatically post-promotion for formal graph validation (Gate P5-C). |
| `tests/test_phase5.py` | NEW | End-to-end testing of guardrail bounds, manifest lifecycle, and executor actions. |
| `docs/PHASE5_IMPLEMENTATION_NOTES.md` | NEW | This document. |

### Modified Files

| File | Change |
|------|--------|
| `models/promotion.py` | Extended formal classes to include `PromotionPlan`, `PromotionResult`, `PromotionAuditRecord`. Added `lifecycle_status` to `PromotionManifest`. |
| `cli.py` | Added Phase-5-native command `execute-promotion`. Modified `check-promotion` (Phase 4) to include absolute source and target paths directly inside the manifest dictionary. |
| `README.md` | Updated architecture breakdown and Status flags to reflect Phase 5 delivery. |

### Architecture Decisions

1. **Manifest is the source of truth for execution** — To prevent data drift, the executor relies strictly on the paths pre-calculated and embedded inside the Phase 4 `PromotionManifest` (added via TD-P4-x cleanup). It only targets artifacts that have `"passed"` the promotion checks.
2. **Hard boundary fencing via Guardrail** — The `PromotionGuardrail` explicitly enforces a directory jail. Moving any file to unapproved locations in formal (such as overwriting `freeze_gate_status.yaml` or writing to `examples/`) results in an immediate and fatal stop (Gate P5-B).
3. **Immutability of Audit Ledgers** — Successful or partially-failed promotions append entry hashes to `formal_promotions_log.yaml`. We do not rely on Git for application-level event auditing.
4. **No Formal Freeze Execution** — This phase only implements the *physical population path*. It specifically abstains from editing `freeze_gate_status.yaml` (Gate P5-D).

### Test Results

- Post-Phase 5 baseline: all project tests pass (Phase 5 test suite expanded to 10+ tests).
- 0 regressions identified.
- Rollback Policy: Strict Preflight / No Partial Write by Design.

### Technical Debt Closed (P4 -> P5)

1. **Manifest Clean-up**: Added lifecycle markers directly to `manifest.yaml` (lifecycle: pending/promoted/expired) ensuring manifests aren't re-used circularly.
2. **Naming Convention decoupling in executor**: Executor no longer guesses file names based on UUID. It directly uses the explicit path assignments set by Phase 4 checking logic.

---

*Phase 5 establishes the accepted physical population path into the formal baseline boundary. The next repository step is Phase 6 planning re-review against `docs/PHASE6_ARCHITECTURE_PLAN.md` before any new implementation work begins.*
