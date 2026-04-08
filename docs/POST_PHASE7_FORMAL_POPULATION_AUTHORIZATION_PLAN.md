# Post-Phase-7 Formal Population Authorization Plan

**Document ID:** APLH-PLAN-POST-P7-AUTHORIZATION  
**Version:** 1.0.1  
**Date:** 2026-04-07  
**Status:** Planning Accepted  
**Package Name:** Post-Phase7 Formal Population Authorization

---

## 1. Planning Decision

The smallest correct governed package after Phase 7 acceptance is:

# Post-Phase7 Formal Population Authorization

This is not Phase 8. It is not freeze-review intake. It is not a real formal population execution session.

Phase 7 accepted the controlled `populate-formal` mechanism, but the repository still lacks a reviewed authorization record that may be passed to that mechanism. The next missing governance object is therefore the **authorization packet**: the evidence, human approval boundary, and execution separation rules required before any real `populate-formal` run against the checked-in formal root.

---

## 2. Current Repository Reality

The planning baseline starts from this repository state:

- Phase 7 is accepted.
- The real checked-in formal baseline is still `unpopulated`.
- Formal source counts remain zero for `requirements`, `functions`, `interfaces`, `abnormals`, `glossary`, and `trace`.
- `modes`, `transitions`, and `guards` are absent from the formal root.
- No reviewed Phase 7 population approval YAML exists for a real formal population run.
- `MANIFEST-20260407045109.yaml` remains `overall_status: blocked`, `promotion_decision: pending_review`, and `lifecycle_status: pending`.
- `artifacts/.aplh/freeze_gate_status.yaml` remains manual-only and unchanged.
- `freeze-complete` has not been declared.
- `accepted_for_review` and `pending_manual_decision` have not been automatically set.

The Phase 7 mechanism may be used only after a reviewed approval exists. This planning package does not create that approval.

---

## 3. Why This Is the Smallest Correct Next Step

The next package should not be an alignment package because the live Phase 7 policy mismatch was already fixed and accepted:

- `promotion_policy.py` uses accepted `Transition.guard`.
- `guard_id` may remain in historical notes or historical modules, but it is no longer the live Phase 7 policy path.

The next package should not be a controlled real-population execution package yet because:

- no reviewed approval YAML exists
- real population would write formal artifact truth
- `populate-formal` intentionally creates audit and manifest records during an authorized successful population
- the project still needs a reviewable record that says exactly who approved the run, what inventory was approved, and what evidence was cited

The next package should not be freeze-review intake because:

- the formal baseline remains `unpopulated`
- Phase 6 `G6-A`, `G6-B`, `G6-D`, and `G6-E` still do not pass for the real repository
- freeze-review intake must come after real population and post-validation, not before them

Therefore, the next package is a formal population authorization package.

---

## 4. Package Definition

Post-Phase7 Formal Population Authorization defines the approval boundary for one future controlled population run.

It must answer:

- what exact inventory is being authorized
- what evidence supports the approval
- who may approve the population
- where the approval YAML may live
- how execution must prove it is using the reviewed approval
- what must remain forbidden until after real population and re-assessment

This planning package does not itself create:

- executable approval YAML
- formal artifacts
- promotion audit records
- population audit records
- manual review-intake state
- freeze signoff state

---

## 5. Approval Representation

The executable approval record must use the existing `FormalPopulationApproval` model:

- `approval_id`
- `approved_by`
- `approved_at`
- `decision: approved`
- `source_baseline_dir`
- `formal_baseline_dir`
- `allowed_source_dirs`
- `expected_file_count`
- `evidence_refs`
- `notes`

Recommended location for a future approved record:

- `artifacts/.aplh/formal_population_approvals/`

Reason:

- the record is governance authorization, not artifact truth
- it is scoped to the formal root
- it is separated from demo source artifacts and formal artifact directories
- it can be passed explicitly to `populate-formal --approval`

Important boundary:

- A file that conforms to `FormalPopulationApproval` and has `decision: approved` is executable by the current Phase 7 mechanism.
- Therefore this planning package must not create a real approval YAML.
- Any future draft approval must live as non-executable documentation until an independent approval step explicitly creates the executable YAML.

---

## 6. Required Evidence for Future Approval

A future executable approval must cite reviewable evidence for:

1. Phase 7 mechanism acceptance:
   - [`docs/PHASE7_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_REVIEW_REPORT.md)
2. Phase 7 implementation summary:
   - [`docs/PHASE7_IMPLEMENTATION_NOTES.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_IMPLEMENTATION_NOTES.md)
3. Phase 7 planning contract:
   - [`docs/PHASE7_FORMAL_POPULATION_PLAN.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_FORMAL_POPULATION_PLAN.md)
4. The exact source inventory:
   - a deterministic inventory report generated by the Phase 7 mechanism or by a future review packet
5. The expected file count:
   - must match `FormalPopulationExecutor.build_inventory()`
6. The allowed source directories:
   - must exactly match `FormalPopulationExecutor.ALLOWED_SOURCE_DIRS`
7. The execution command:
   - must target `--dir artifacts`
   - must target `--demo artifacts/examples/minimal_demo_set`
   - must pass the explicitly reviewed approval path

The approval must not cite runtime traces, scenarios, or `.aplh` governance records as formal artifact truth.

---

## 7. Proposed Gates

| Gate | Tier | Purpose | Pass Condition |
|---|---|---|---|
| `P7A-G1 Inventory Evidence Freeze` | T1 | Freeze the exact source inventory for the future approval | Inventory is deterministic, allowlisted, and excludes scenarios, demo runtime traces, `.aplh`, and freeze files |
| `P7A-G2 Approval Authority Boundary` | T1 | Prevent implementation from self-approving a real population | Executable `FormalPopulationApproval` YAML may be created only after independent approval |
| `P7A-G3 Approval Schema Match` | T1 | Ensure approval can be used by Phase 7 without ad hoc interpretation | Approval fields match the existing `FormalPopulationApproval` model and exact allowlist |
| `P7A-G4 Execution Separation` | T1 | Keep approval planning separate from real population writes | No `populate-formal` run against checked-in `artifacts/` occurs in planning or planning review |
| `P7A-G5 Phase 6 State Preservation` | T1 | Keep state classification honest before real population | Real repository remains `unpopulated` until the approved population run actually completes and is re-assessed |
| `P7A-GZ Freeze Isolation` | T3 | Keep freeze manual-only | `freeze_gate_status.yaml` remains unchanged; no `freeze-complete`, `accepted_for_review`, or `pending_manual_decision` is set |

---

## 8. Future Work Authorized Only After Planning Acceptance

If this planning package is independently accepted, a later bounded execution session may create a **non-executable approval request packet** that contains:

- exact inventory snapshot
- expected file count
- evidence references
- proposed approval metadata
- proposed `populate-formal` command
- preflight checklist
- rollback / no-overwrite expectations
- explicit statement that it is not itself an executable `FormalPopulationApproval`

That future session still must not run `populate-formal` against the checked-in formal root.

Creating the executable `FormalPopulationApproval` YAML should be a separate independent approval action, not an implementation convenience.

---

## 9. Explicit Out of Scope

This planning package must not:

- modify `artifacts/.aplh/freeze_gate_status.yaml`
- declare `freeze-complete`
- create executable `FormalPopulationApproval` YAML
- run `populate-formal` against checked-in `artifacts/`
- populate formal artifacts
- create `formal_population_audit_log.yaml`
- create `formal_promotions_log.yaml`
- create a promoted manifest in the real demo `.aplh/promotion_manifests/` area
- set `accepted_for_review`
- set `pending_manual_decision`
- start Phase 8 implementation
- enter freeze-review intake
- expand APLH into production runtime, certification package, UI, dashboard, or platform
- reopen accepted schema, trace, graph, validator, evaluator, or runtime boundaries

---

## 10. Independent Review Result

This planning package has been independently reviewed and accepted.

Review:

- Session: `APLH-PostPhase7-Authorization-Planning-Review`
- Review input: [`docs/POST_PHASE7_AUTHORIZATION_PLANNING_REVIEW_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_AUTHORIZATION_PLANNING_REVIEW_INPUT.md)
- Review report: [`docs/POST_PHASE7_AUTHORIZATION_PLANNING_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_AUTHORIZATION_PLANNING_REVIEW_REPORT.md)
- Conclusion: `Planning Accepted`

Next session:

- Session: `APLH-PostPhase7-Authorization-Request-Package`
- Handoff: [`docs/POST_PHASE7_AUTHORIZATION_REQUEST_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_AUTHORIZATION_REQUEST_INPUT.md)
- Recommended model: `GPT-5.4`
- GPT-5.4 fallback: `GLM-5-Turbo` -> `Gemini 3.1 Pro`

---

## 11. Final Status

Current status after this package:

- `Post-Phase7 Formal Population Authorization Planning Accepted`

This state authorizes a future bounded request-package session only. It does not authorize executable approval YAML creation, real formal population, freeze-review intake, Phase 8 implementation, or `freeze-complete`.
