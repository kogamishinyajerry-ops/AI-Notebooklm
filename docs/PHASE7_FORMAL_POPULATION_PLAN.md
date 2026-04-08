# APLH Phase 7 Formal Baseline Population Plan

**Document ID:** APLH-PLAN-P7-FORMAL-POPULATION  
**Version:** 1.0.1  
**Date:** 2026-04-07  
**Status:** Planning Accepted  
**Source Baseline:** Repository reality after Phase 6 acceptance

---

## 1. Planning Decision

The next governed package after Phase 6 acceptance should be:

# Phase 7 Formal Baseline Population

This document is a planning contract. Phase 7 implementation authority comes only from the independent `Planning Accepted` record.

This package is intentionally narrower than a general Phase 7 runtime, certification, UI, dashboard, or platformization effort. Its single purpose is to plan how APLH should move from an accepted Phase 6 governance mechanism to a real, corroborated formal baseline population.

Planning acceptance record:

- [`docs/PHASE7_PLANNING_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_PLANNING_REVIEW_REPORT.md)

---

## 2. Why This Is the Smallest Correct Next Step

Phase 6 is accepted, but the formal baseline is still `unpopulated`.

The repository state shows that:

- `artifacts/requirements/`, `artifacts/functions/`, `artifacts/interfaces/`, `artifacts/abnormals/`, `artifacts/glossary/`, and `artifacts/trace/` currently contain zero formal YAML files.
- `artifacts/modes/`, `artifacts/transitions/`, and `artifacts/guards/` are not populated in the formal baseline.
- `artifacts/.aplh/formal_promotions_log.yaml` is absent.
- `artifacts/examples/minimal_demo_set/.aplh/promotion_manifests/MANIFEST-20260407045109.yaml` remains `overall_status: blocked` and `lifecycle_status: pending`.
- `artifacts/.aplh/freeze_readiness_report.yaml` reports `formal_state: unpopulated`, `population_state: unpopulated`, `validation_state: not_validated`, and `review_preparation_state: not_ready`.
- `artifacts/.aplh/freeze_gate_status.yaml` remains manual-only with all freeze gate booleans `false` and signer `PENDING`.

Therefore, the project cannot honestly move to freeze-review intake yet. It must first plan the formal population step.

The next package is not:

- a freeze-complete package
- a manual freeze review package
- a runtime package
- a certification package
- a UI or dashboard package
- a generic Phase 7 expansion

It is the minimal planning package needed to make formal population executable and reviewable without hiding that the current formal root is still empty.

---

## 3. Current Artifact Inventory

The current formal artifact source directories are empty. The formal root also contains `artifacts/examples/` as the demo baseline location, but that nested demo tree is not formal artifact source truth.

| Formal Directory | Current YAML Count | Notes |
|---|---:|---|
| `artifacts/requirements/` | 0 | Empty formal P0/P1 source directory |
| `artifacts/functions/` | 0 | Empty formal P0/P1 source directory |
| `artifacts/interfaces/` | 0 | Empty formal P0/P1 source directory |
| `artifacts/abnormals/` | 0 | Empty formal P0/P1 source directory |
| `artifacts/glossary/` | 0 | Empty formal P0/P1 source directory |
| `artifacts/trace/` | 0 | Empty formal trace directory |
| `artifacts/modes/` | 0 | Missing or empty Phase 2A formal directory |
| `artifacts/transitions/` | 0 | Missing or empty Phase 2A formal directory |
| `artifacts/guards/` | 0 | Missing or empty Phase 2A formal directory |

The current demo baseline has a complete demo-scale source set:

| Demo Directory | Current File Count | Role |
|---|---:|---|
| `artifacts/examples/minimal_demo_set/requirements/` | 2 | Supporting formal source candidate |
| `artifacts/examples/minimal_demo_set/functions/` | 3 | Supporting formal source candidate |
| `artifacts/examples/minimal_demo_set/interfaces/` | 2 | Supporting formal source candidate |
| `artifacts/examples/minimal_demo_set/abnormals/` | 1 | Supporting formal source candidate |
| `artifacts/examples/minimal_demo_set/glossary/` | 3 | Supporting formal source candidate |
| `artifacts/examples/minimal_demo_set/trace/` | 29 | Supporting formal trace candidate |
| `artifacts/examples/minimal_demo_set/modes/` | 3 | Phase 2A promotion candidate |
| `artifacts/examples/minimal_demo_set/transitions/` | 3 | Phase 2A promotion candidate |
| `artifacts/examples/minimal_demo_set/guards/` | 3 | Phase 2A promotion candidate |
| `artifacts/examples/minimal_demo_set/scenarios/` | 7 | Demo execution evidence only; not formal artifact truth |

Planning probe:

- A temporary full-source copy of demo artifact directories into a temporary formal root passed `validate-artifacts` and `check-trace`.
- The same temporary full-source copy still reported `formal_state: unpopulated` through Phase 6 readiness machinery because there was no promoted manifest and no promotion audit corroboration for the Phase 2A artifacts.
- A temporary copy of only `modes/`, `transitions/`, and `guards/` failed trace/consistency because supporting P0/P1 artifacts and trace links were absent.

Planning implication:

- Formal population cannot be reduced to copying `modes/`, `transitions`, and `guards` alone.
- Formal population also cannot be reduced to raw manual copying, because Phase 6 classification requires corroborated manifest and audit evidence before `populated` can be claimed.

---

## 4. Phase 7 Definition

Phase 7 is the **formal baseline population planning and execution-readiness phase**.

It plans how to populate the formal root from the accepted demo baseline through a reviewable, auditable, machine-validated process.

Phase 7 should move the project from:

- `Phase 6 Accepted`
- real formal state `unpopulated`
- blocked / pending demo manifest

to a state where a later implementation session can safely produce:

- a reviewed formal population source set
- a ready promotion or population manifest
- a formal promotion audit trail
- formal artifact YAMLs under the formal baseline root
- a Phase 6 readiness packet that can honestly claim `populated` and, if validation passes, `post-validated`

Phase 7 must still stop before:

- `accepted_for_review`
- `pending_manual_decision`
- `freeze-complete`

unless a later accepted plan explicitly routes a human-only review-intake step.

---

## 5. Formal Population Data Contract

Phase 7 must distinguish two artifact planes.

### 5.1 Supporting Formal Source Plane

These artifacts are required for formal validation and trace consistency but are not currently part of the Phase 5/6 Phase 2A promotion-only candidate surface:

- `requirements/`
- `functions/`
- `interfaces/`
- `abnormals/`
- `glossary/`
- `trace/`

Phase 7 implementation must not silently copy these files. It must either:

1. introduce a reviewed and audited supporting-source population path, or
2. block execution until a human-approved formal source set already exists.

The planning recommendation is option 1: add a narrow formal-source population path with an explicit allowlist, manifest evidence, and audit logging.

### 5.2 Phase 2A Promotion Plane

These artifacts drive Phase 6 `populated` classification:

- `modes/`
- `transitions/`
- `guards/`

Phase 7 must keep these Phase 2A artifacts tied to:

- a ready manifest
- a human promotion decision
- an execution audit log
- post-population validation

Raw files in those directories without manifest/audit corroboration must continue to be treated as insufficient for `populated`.

### 5.3 Evidence Plane

These records remain evidence only:

- demo `.aplh/traces/`
- demo `.aplh/handoffs/`
- demo `.aplh/review_signoffs.yaml`
- demo scenarios under `scenarios/`
- `artifacts/.aplh/freeze_readiness_report.yaml`
- `artifacts/.aplh/advisory_resolutions.yaml`
- `artifacts/.aplh/acceptance_audit_log.yaml`

They must not become formal artifact truth.

---

## 6. Known Planning Blockers for Phase 7 Implementation

### P7-BLK-1: Current manifest is blocked

`MANIFEST-20260407045109.yaml` is not executable because it remains:

- `overall_status: blocked`
- `promotion_decision: pending_review`
- `lifecycle_status: pending`

Phase 7 implementation must not call `execute-promotion` against a blocked manifest.

### P7-BLK-2: Demo signoff coverage is incomplete for current promotion policy

A temporary non-mutating `check-promotion` run against copied inputs showed that many candidates still fail demo evidence coverage.

Phase 7 implementation must not fake signoffs. It must either:

- generate the missing coverage through accepted demo scenarios and real signoff flow, or
- add a separately reviewed manual promotion-approval record that is explicitly scoped to formal population and does not claim freeze.

### P7-BLK-3: Transition guard policy uses a stale field name

Current demo transition YAML uses the accepted `guard` field, for example:

- `guard: "GUARD-0001"`
- `guard: "GUARD-0002"`
- `guard: "GUARD-0003"`

The current promotion policy check still looks for `guard_id`, causing transitions to fail even when they have a valid accepted `guard` field.

Phase 7 implementation may fix this policy mismatch only after this planning package is independently accepted. The fix must preserve the accepted `Transition.guard` schema and must not introduce `guard_id` as a new live schema field.

### P7-BLK-4: Formal P0/P1 and trace source truth is empty

Formal population of only Phase 2A artifacts is insufficient because Mode, Transition, and Guard artifacts reference supporting Requirements, Functions, Interfaces, Abnormals, and TraceLinks.

Phase 7 must plan population for the full formal source set, not just the Phase 2A state-machine layer.

---

## 7. Proposed Milestones

### P7-M0: Planning Package

Deliverables:

- this plan
- `docs/PHASE7_PLANNING_REVIEW_INPUT.md`
- README state sync
- docs index sync

Exit condition:

- independent planning reviewer can judge whether this package is sufficiently bounded to authorize implementation planning.

### P7-M1: Formal Source Set Contract

Deliverables for a future implementation session:

- exact source directory allowlist
- exact target directory allowlist
- explicit exclusion of scenarios, demo runtime traces, `.aplh` governance records, and freeze files from formal artifact truth
- deterministic inventory report for the source set
- policy for handling existing formal files if any are present

Exit condition:

- there is no ambiguity about which files may be populated into formal artifact directories.

### P7-M2: Promotion Policy Repair and Evidence Intake

Deliverables for a future implementation session:

- repair the stale `guard_id` check to use the accepted `Transition.guard` field
- preserve the accepted schema without introducing `guard_id`
- require either demo signoff coverage or a reviewed population-approval record
- keep all review evidence non-authoritative over artifact truth

Exit condition:

- a new manifest or population intake record can become `ready` only when evidence and policy checks pass.

### P7-M3: Controlled Population Execution Plan

Deliverables for a future implementation session:

- audited write path for supporting formal source artifacts
- audited write path for Phase 2A promotion artifacts
- no writes to `freeze_gate_status.yaml`
- no writes outside the formal artifact allowlist
- no promotion execution unless the manifest or intake record is ready and approved

Exit condition:

- formal files can be populated with audit evidence and without untracked manual copy.

### P7-M4: Post-Population Validation and Phase 6 Readiness Re-Assessment

Deliverables for a future implementation session:

- `validate-artifacts --dir artifacts`
- `check-trace --dir artifacts`
- `assess-readiness --dir artifacts --demo artifacts/examples/minimal_demo_set`
- proof that Phase 6 state classification is not bypassed

Exit condition:

- the formal baseline can truthfully report `populated`
- if validation passes, the formal baseline can truthfully report `post-validated`
- `ready_for_freeze_review` may be reported only if Phase 6 `G6-D` conditions are met
- no manual review intake or freeze-complete is claimed automatically

---

## 8. Gate Design

| Gate | Tier | Purpose | Pass Condition |
|---|---|---|---|
| `G7-A Source Inventory Freeze` | T1 | Freeze the exact source and target artifact inventory | Source and target paths are deterministic, allowlisted, and exclude `.aplh`, scenarios, runtime traces, and freeze files |
| `G7-B Policy Alignment` | T1 | Align promotion policy with accepted schemas | Transition guard policy uses `Transition.guard`; no `guard_id` field is introduced |
| `G7-C Evidence Intake` | T1/T2 | Require reviewable evidence before population | Candidates are backed by demo signoffs or an explicit reviewed population-approval record |
| `G7-D Sandbox Validation` | T1 | Prove the planned formal source set validates before real writes | Temporary formal root passes schema, trace, and consistency checks for the planned set |
| `G7-E Controlled Population Write` | T1 | Bound real file writes | Writes are limited to approved formal artifact directories and are audit logged |
| `G7-F Phase 6 Re-Assessment` | T1 | Re-enter accepted Phase 6 classifier after population | `assess-readiness` reports the new state without manual override or freeze mutation |
| `G7-Z Freeze Isolation` | T3 | Keep freeze manual-only | `freeze_gate_status.yaml` remains unchanged unless a later human freeze authority explicitly edits it |

---

## 9. Allowed Future Implementation Surfaces

If this planning package is accepted, a future implementation session may touch:

- `aero_prop_logic_harness/services/promotion_policy.py`
- `aero_prop_logic_harness/services/evidence_checker.py`
- `aero_prop_logic_harness/services/promotion_guardrail.py`
- `aero_prop_logic_harness/services/promotion_executor.py`
- `aero_prop_logic_harness/services/promotion_manifest_manager.py`
- `aero_prop_logic_harness/services/promotion_audit_logger.py`
- `aero_prop_logic_harness/services/formal_population_checker.py`
- `aero_prop_logic_harness/services/freeze_review_preparer.py`
- `aero_prop_logic_harness/models/promotion.py`
- `aero_prop_logic_harness/cli.py`
- `tests/`
- `docs/`

Any implementation must remain minimal and must be traceable to a Phase 7 gate above.

---

## 10. Explicit Out of Scope

Phase 7 planning and any later Phase 7 implementation must not:

- modify `artifacts/.aplh/freeze_gate_status.yaml`
- declare `freeze-complete`
- automatically set `accepted_for_review` or `pending_manual_decision`
- treat `.aplh` governance records as artifact source-of-truth
- populate `scenarios/` into the formal baseline as source truth
- promote demo runtime traces from `.aplh/traces/` as formal trace links
- reopen schema, trace, graph, validator, evaluator, or runtime contracts
- reintroduce `predicate_expression`
- introduce `TRANS -> FUNC` or `TRANS -> IFACE` trace directions
- turn `TRANS.actions` or `Function.related_transitions` into consistency-scope drivers
- turn APLH into production runtime, certification package, UI, dashboard, or platform

---

## 11. Independent Planning Review Result

This package has passed independent planning review.

Review session:

- `APLH-Phase7-Planning-Review`

Review conclusion:

- `Planning Accepted`

Acceptance record:

- [`docs/PHASE7_PLANNING_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_PLANNING_REVIEW_REPORT.md)

Bounded implementation may proceed in `APLH-Phase7-Exec`. The implementation remains constrained by this plan and must not declare `freeze-complete`.

---

## 12. Current Status

Current status after this planning package:

- `Phase 7 Planning Accepted`

This status does not change the actual formal baseline state. The real formal baseline remains `unpopulated`.
