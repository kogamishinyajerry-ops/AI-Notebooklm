# Post-Phase-7 Corrected Inventory Approval Plan

**Document ID:** APLH-PLAN-POST-P7-CORRECTED-INVENTORY-APPROVAL  
**Version:** 1.0.0  
**Date:** 2026-04-07  
**Status:** Planning Accepted  
**Planning Session:** `APLH-PostPhase7-Corrected-Inventory-Approval-Planning`

---

## 0. Overall Decision

The next package is:

- **Post-Phase7 Corrected Inventory Approval**

This is the smallest correct next step after the controlled population blocker was resolved.

The `ABN-0001` sandbox coverage blocker has been fixed in the demo source set, but the fix added `TRACE-0030` and changed the controlled population source inventory from `49` files to `50` files. The existing executable approval `FORMAL-POP-APPROVAL-20260407-001` approved the earlier `49`-file inventory and is now stale for any future controlled population attempt.

This planning package does not approve the corrected inventory, does not create a new executable approval YAML, does not run `populate-formal`, and does not populate the checked-in formal baseline.

Recommended next gate:

- `APLH-PostPhase7-Corrected-Inventory-Approval-Request-Package`

Recommended next package if planning is accepted:

- `APLH-PostPhase7-Corrected-Inventory-Approval-Request-Package`

Acceptance record:

- [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_REPORT.md)

---

## 1. Current Repository Reality

Authoritative status:

- Phase 7 implementation is accepted.
- Post-Phase7 formal population authorization planning is accepted.
- The first non-executable authorization request package was accepted.
- One executable approval YAML was created at `artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml`.
- One controlled `populate-formal` command was run and blocked during sandbox validation before any formal writes.
- The `ABN-0001` coverage blocker is now resolved in the demo source set.
- The corrected source inventory is now `50` files.
- The old approval is bounded to `expected_file_count: 49`.
- The checked-in formal baseline remains unpopulated.
- `artifacts/.aplh/freeze_gate_status.yaml` remains manual-only.
- `freeze-complete`, `accepted_for_review`, and `pending_manual_decision` remain unset.

Authoritative blocker-resolution report:

- [`docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md)

Stale approval:

- [`artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml)

---

## 2. Why Re-Approval Is Required

The original approval was not a blanket approval to populate any future version of the demo source set. It was a specific approval over a specific inventory.

The corrected source set changed the approved population input:

- `trace-0030.yaml` was added.
- live inventory changed from `49` to `50`.
- the trace directory count changed from `29` to `30`.
- `ABN-0001` and `MODE-0002` now carry explicit coverage linkage.

That is a material governance change. Even though the change fixes a validator blocker and is semantically correct, it still changes the approved source set. A new approval path is required before another controlled population execution may run.

The re-approval requirement protects:

- inventory integrity
- evidence traceability
- no-overwrite assumptions
- approval authority separation
- the audit distinction between the failed 49-file attempt and the corrected 50-file attempt

---

## 3. Why The Old Approval Cannot Be Edited In Place

`FORMAL-POP-APPROVAL-20260407-001.yaml` must not be edited in place.

Reasons:

- It is an executed approval artifact. It was already used for the one authorized controlled population attempt that returned `rc=1` before formal writes.
- Its `expected_file_count: 49` is part of the approval decision evidence.
- Editing it to `50` would rewrite approval history after the source set changed.
- In-place editing would collapse blocker resolution, re-approval, and execution authority into one hidden action.
- It would make the previous failed attempt harder to audit.

Required handling:

- Keep `FORMAL-POP-APPROVAL-20260407-001.yaml` in place.
- Treat it as historical, executable-shaped, but stale for corrected inventory.
- Do not delete it.
- Do not mutate it.
- Do not use it for a future `populate-formal` command.
- Create a new approval ID only after corrected-inventory request and approval gates pass.

---

## 4. Corrected Inventory Baseline

Corrected inventory count:

- `50`

Allowed source directory order:

1. `requirements`
2. `functions`
3. `interfaces`
4. `abnormals`
5. `glossary`
6. `trace`
7. `modes`
8. `transitions`
9. `guards`

Corrected directory counts:

| Directory | Count |
|---|---:|
| `requirements` | 2 |
| `functions` | 3 |
| `interfaces` | 2 |
| `abnormals` | 1 |
| `glossary` | 3 |
| `trace` | 30 |
| `modes` | 3 |
| `transitions` | 3 |
| `guards` | 3 |
| **Total** | **50** |

The only inventory-count change from the stale approval path is the added trace:

- [`artifacts/examples/minimal_demo_set/trace/trace-0030.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/trace/trace-0030.yaml)

Corrected coverage relationship:

- [`artifacts/examples/minimal_demo_set/abnormals/abn-0001.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/abnormals/abn-0001.yaml) now references `MODE-0002`.
- [`artifacts/examples/minimal_demo_set/modes/mode-0002.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/modes/mode-0002.yaml) now references `ABN-0001`.
- [`artifacts/examples/minimal_demo_set/trace/trace-0030.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/trace/trace-0030.yaml) records `ABN-0001 -> MODE-0002` with `link_type: "triggers_mode"`.

Validation evidence:

- `validate-artifacts` passes on `artifacts/examples/minimal_demo_set`.
- `check-trace` passes on `artifacts/examples/minimal_demo_set`.
- non-mutating sandbox validation passes on the corrected source inventory.
- old approval inventory validation fails with `49 != 50`.

---

## 5. Proposed New Approval Identity

Recommended new approval ID:

- `FORMAL-POP-APPROVAL-20260407-002`

Recommended future path, if and only if a later independent approval action grants it:

- `artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-002.yaml`

This plan does not create that YAML.

The future executable approval, if granted, should include at least:

- `approval_id: "FORMAL-POP-APPROVAL-20260407-002"`
- `decision: "approved"`
- same allowed source directory order used by `FormalPopulationExecutor.ALLOWED_SOURCE_DIRS`
- `expected_file_count: 50`
- evidence references to this plan, the corrected-inventory planning review report, the corrected request packet, the corrected request review report, and the blocker-resolution report
- a note that it supersedes `FORMAL-POP-APPROVAL-20260407-001` only for corrected inventory execution authority

---

## 6. Supersession Handling

Supersession is required conceptually, but not as a new executable YAML during this planning package.

Decision:

- `FORMAL-POP-APPROVAL-20260407-001.yaml` remains in place as a historical stale approval.
- This plan and its independent planning review serve as the first non-executable supersession record.
- A future corrected-inventory request packet must repeat the supersession statement.
- A future approval action report must explicitly state whether `FORMAL-POP-APPROVAL-20260407-002` supersedes `FORMAL-POP-APPROVAL-20260407-001` for the corrected `50`-file inventory.
- No standalone supersession YAML is required before the corrected request packet.

If a standalone supersession record is introduced later, it must be non-executable and must not conform to `FormalPopulationApproval`. It must not be valid input to:

```bash
python -m aero_prop_logic_harness populate-formal --approval <path>
```

---

## 7. Gates Before Any New Executable Approval YAML

### CIPA-G1: Corrected Inventory Validation

The corrected source inventory must pass:

- `validate-artifacts`
- `check-trace`
- non-mutating sandbox validation through `FormalPopulationExecutor.validate_sandbox()`

The expected inventory must remain:

- total `50`
- trace count `30`
- no additional source files beyond the accepted allowlist

### CIPA-G2: Stale Approval Isolation

The old approval must remain:

- present
- unedited
- not deleted
- not reused
- documented as stale for corrected inventory

### CIPA-G3: Evidence Closure

The corrected request packet must cite:

- blocker-resolution report
- `trace-0030.yaml`
- `abn-0001.yaml`
- `mode-0002.yaml`
- original blocked execution report
- old approval action report
- Phase 7 acceptance report
- corrected-inventory planning review report

### CIPA-G4: Request/Review/Approval Separation

The next package after planning acceptance must be a corrected-inventory request package, not an approval action.

Required sequence:

1. corrected-inventory approval planning
2. independent planning review
3. corrected-inventory non-executable request package
4. independent request package review
5. separate independent approval action
6. separate controlled population execution
7. independent controlled population review

### CIPA-G5: No Real Writes Before Approval

Until a future independent approval action creates the new executable approval YAML:

- do not run `populate-formal`
- do not manually copy formal artifacts
- do not create `formal_population_audit_log.yaml`
- do not create `formal_promotions_log.yaml`
- do not create a promoted manifest

### CIPA-GZ: Freeze Isolation

All future corrected-inventory steps must continue to preserve:

- no modification to `artifacts/.aplh/freeze_gate_status.yaml`
- no `freeze-complete`
- no `accepted_for_review`
- no `pending_manual_decision`
- no freeze-review intake before a successful controlled population has been independently reviewed

---

## 8. Out Of Scope

This planning package does not:

- create `artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-002.yaml`
- edit `FORMAL-POP-APPROVAL-20260407-001.yaml`
- delete old approval YAML
- run `populate-formal`
- hand-copy formal artifacts into `artifacts/`
- create `formal_population_audit_log.yaml`
- create `formal_promotions_log.yaml`
- create a promoted manifest
- enter freeze-review intake
- declare `freeze-complete`
- set `accepted_for_review`
- set `pending_manual_decision`
- start Phase 8
- weaken validators
- reopen accepted schema, trace, graph, evaluator, or runtime boundaries

---

## 9. Independent Planning Review Acceptance Criteria

The planning review may return `Planning Accepted` only if all of the following hold:

- the plan treats the `ABN-0001` blocker as fixed
- the plan freezes the corrected inventory as `50`
- the plan identifies `FORMAL-POP-APPROVAL-20260407-001` as stale for corrected inventory
- the plan forbids editing or deleting the old approval
- the plan forbids reusing the old approval for another population attempt
- the plan proposes a new approval identity without creating executable approval YAML
- the plan documents supersession without introducing a new executable artifact
- the plan preserves request, review, approval, and execution separation
- the plan preserves formal baseline, `.aplh`, and freeze isolation boundaries
- the repo contains no formal artifact truth writes, no formal population audit log, no formal promotions log, and no new promoted manifest

If any of those conditions fail, the review must return `Revision Required`.

---

## 10. Final Recommendation

Planning recommendation:

- `Corrected-Inventory Approval Planning Package Accepted`

Next session:

- `APLH-PostPhase7-Corrected-Inventory-Approval-Request-Package`

Recommended model:

- `GPT-5.4`

Fallback:

- `GLM-5-Turbo` -> `Gemini 3.1 Pro`

Why:

- the corrected source set is validator-clean but changes the approved inventory
- the old approval must remain immutable historical evidence
- a new approval path must be reviewed before another controlled population attempt
- real population and freeze-review intake remain out of scope until the corrected approval path is accepted and executed under a separate session
