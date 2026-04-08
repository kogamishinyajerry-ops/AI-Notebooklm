# Phase 6 Architecture Plan

**Document ID:** APLH-PLAN-P6  
**Version:** 1.0.0  
**Date:** 2026-04-07  
**Status:** Planning Accepted  
**Source Baseline:** Repository reality as of 2026-04-07

---

## 1. Overall Conclusion

### 1.1 Planning Decision

Phase 6 planning is allowed to proceed because:

- Phase 5 is accepted per `docs/PHASE5_REVIEW_REPORT.md`.
- Phase 5 machinery already exists in-repo (`promotion_manifest_manager`, `promotion_guardrail`, `promotion_executor`, `formal_population_checker`, `promotion_audit_logger`, `readiness_assessor`).
- The prior blocker was not route confusion. It was the absence of a repository-backed Phase 6 planning contract. This document, together with `docs/PHASE6_REREVIEW_INPUT.md`, closed that gap and has now been accepted by `docs/PHASE6_PLAN_REVIEW_REPORT.md`.

### 1.2 Single Valid Definition of Phase 6

Phase 6 is the **formal population governance and freeze-review preparation phase**.

It is the phase that takes the accepted Phase 5 physical promotion path and freezes how the project moves from:

- `blocked/pending manifest`
- to `promoted`
- to `populated`
- to `post-validated`
- to `ready_for_freeze_review`

without claiming `freeze-complete`.

Phase 6 does **not** declare freeze, does **not** auto-edit `freeze_gate_status.yaml`, and does **not** turn APLH into a runtime platform or certification package.

### 1.3 Repository Reality This Plan Must Explicitly Accept

As of this planning backfill:

- `artifacts/.aplh/freeze_gate_status.yaml` is still all `false` / `PENDING`.
- The formal baseline does not currently contain `artifacts/modes/`, `artifacts/transitions/`, or `artifacts/guards/`.
- The only observed promotion manifest under the demo baseline is `MANIFEST-20260407045109.yaml`, and its `overall_status` is `blocked`.
- Phase 5 machinery exists, but formal population has not actually occurred.
- README and docs index state required explicit Phase 6 resynchronization so the next reviewer can navigate the planning package without relying on chat memory.

### 1.4 Explicitly Forbidden Assumptions

Phase 6 planning must not assume any of the following:

- The formal baseline is already populated.
- `promoted` means `freeze-complete`.
- `populated` means `freeze-complete`.
- `post-validated` means a human freeze decision has happened.
- `ready_for_freeze_review` means the manual review is done.
- Any service may auto-advance `freeze_gate_status.yaml`.
- Phase 6 may reopen frozen Phase 0-5 contracts.
- Phase 6 may introduce product runtime, dashboard, certification packaging, or platformization.

---

## 2. Phase 6 Definition

### 2.1 Goal

Freeze the architecture, governance records, status layering, advisory routing, and review handoff needed to turn accepted Phase 5 machinery into a trustworthy **formal population and freeze-review preparation path**.

### 2.2 Non-Goals

Phase 6 does not include:

- Writing Phase 6 implementation code in this planning pass.
- Declaring `freeze-complete`.
- Editing `freeze_gate_status.yaml` automatically.
- Reworking schema, trace, evaluator, or runtime contracts from accepted phases.
- Reintroducing `predicate_expression`.
- Introducing `TRANS -> FUNC` or `TRANS -> IFACE` trace directions.
- Turning `scenario_engine`, `replay_reader`, `handoff_builder`, or `promotion_executor` into production runtime.
- Building UI, dashboard, service platform, or certification package.

### 2.3 Boundary

Phase 6 sits directly above Phase 5.

- Phase 5 answers: "Can reviewed demo artifacts be physically copied into the formal boundary under guardrails?"
- Phase 6 answers: "How do we classify, validate, govern, and hand off the resulting formal state for independent freeze review?"

### 2.4 Relationship to Phase 5 and Later Phases

- Phase 5 remains the only accepted phase that performs actual promotion.
- Phase 6 must consume Phase 5 outputs without weakening any earlier frozen contract.
- Later phases may only begin after Phase 6 is implemented, re-reviewed, and accepted.
- Phase 6 stops at review preparation. Final freeze remains outside automatic flow.

---

## 3. Module Tree

The Phase 6 planning baseline treats the following modules and records as the working control surface.

| Module / Record | Role | Core / Supporting | Phase 6 Responsibility |
|---|---|---|---|
| `services/promotion_manifest_manager.py` | Manifest lifecycle reader/writer (`pending/promoted/expired`) | Core | Source of manifest state for Phase 6 classification |
| `services/promotion_guardrail.py` | Boundary jail for formal target paths | Core | Must be hardened under ADV-1 |
| `services/promotion_executor.py` | Physical copy executor | Core | Must remain executor-only; cannot become freeze decision engine |
| `services/formal_population_checker.py` | Static post-promotion validators | Core | Must become authoritative source for `post-validated` classification |
| `services/readiness_assessor.py` | Formal readiness reporting | Core | Must be aligned with Phase 6 state vocabulary |
| `services/promotion_audit_logger.py` | Formal promotion ledger | Core | Remains immutable governance log |
| `models/promotion.py` | Readiness / promotion schemas | Core | Existing contract to be consumed, not reopened |
| `models/freeze_status.py` | Manual freeze signoff schema | Core | Remains final manual freeze contract |
| `docs/RICHER_EVALUATOR.md` | Richer evaluator boundary reference | Supporting | Reference only; Phase 6 must not expand it into a platform |
| Demo `.aplh/handoffs/` | Demo evidence bundles | Supporting | Remain evidence inputs, not formal source of truth |
| Demo `.aplh/traces/` | Demo execution traces | Supporting | Remain evidence inputs, not formal source of truth |
| Demo `.aplh/promotion_manifests/` | Candidate manifests | Core evidence | Feed Phase 6 classification and review packet |
| Formal `.aplh/formal_promotions_log.yaml` | Immutable promotion audit log | Core evidence | Corroborates `promoted` state |
| `artifacts/.aplh/freeze_readiness_report.yaml` | Planned Phase 6 governance record | Core deliverable | Formal machine-readable review packet summary |
| `artifacts/.aplh/advisory_resolutions.yaml` | Planned Phase 6 governance record | Core deliverable | Official routing and closure tracking for ADV-1..4 |
| `artifacts/.aplh/acceptance_audit_log.yaml` | Planned Phase 6 governance record | Core deliverable | Manual review intake / handoff acknowledgements |

Phase 6 may add governance records under `.aplh/`. It may not redefine the artifact graph as a governance side effect.

---

## 4. Phase 5 -> Phase 6 Data Contract

### 4.1 Inputs Read by Phase 6

| Input | Fields / Signals Used | Why Phase 6 Reads It |
|---|---|---|
| `PromotionManifest` | `manifest_id`, `formal_baseline_dir`, `source_baseline_dir`, `candidates[].candidate_id`, `candidates[].status`, `candidates[].source_path`, `candidates[].target_path`, `overall_status`, `promotion_decision`, `lifecycle_status` | Candidate intake, blocked/ready/promoted classification, evidence references |
| `formal_promotions_log.yaml` | `timestamp`, `manifest_id`, `files_promoted`, `files_failed`, `status` | Immutable corroboration that a promotion really happened |
| `FormalPopulationChecker.check_integrity()` summary | `schema_validation`, `trace_consistency`, `mode_validator`, `coverage_validator` | Hard source for `post-validated` |
| `ReadinessReport` | `prerequisites`, `blockers`, `overall_status`, `met_count`, `total_count` | Formal readiness evidence and blocker surface |
| Formal artifact YAMLs | Current files under `artifacts/` excluding `.aplh/` | Primary source of truth for formal populated state |
| Demo artifact YAMLs | Current files under `artifacts/examples/minimal_demo_set/` excluding `.aplh/` | Source baseline for manifests and evidence only |
| `freeze_gate_status.yaml` | `baseline_scope`, four booleans, signer, timestamp | Final manual freeze decision input, read-only |

### 4.2 Inputs Explicitly Ignored by Phase 6 Governance Classification

Phase 6 planning freezes the following as **non-authoritative** for formal state promotion:

- `PromotionPlan` model instances. Current repo reality does not rely on them.
- `FormalPopulationChecker.generate_report()` output until implementation explicitly wires it in.
- `TRANS.actions` and `Function.related_transitions` as consistency-scope drivers.
- Any hypothetical `predicate_expression`.
- Demo handoff markdown or text reports as source-of-truth artifacts.
- Any `.aplh` record as permission to auto-change artifact YAML or `freeze_gate_status.yaml`.

### 4.3 Source-of-Truth Hierarchy

The hierarchy for Phase 6 is frozen as follows:

1. Formal artifact YAML under `artifacts/` excluding `.aplh/`
2. Formal trace / consistency / mode / coverage validation results derived from those files
3. Demo artifacts only as source evidence for manifests and handoff bundles
4. `.aplh` governance records as reflections, reports, and audit trails
5. `freeze_gate_status.yaml` as final manual freeze decision record only

`.aplh` never outranks formal artifact YAML.

### 4.4 `.aplh` Governance Writes Allowed by Contract

Phase 6 is allowed to plan machine-written governance reflections only in `.aplh/`, specifically:

- `artifacts/.aplh/freeze_readiness_report.yaml`
- `artifacts/.aplh/advisory_resolutions.yaml`
- `artifacts/.aplh/acceptance_audit_log.yaml`
- existing `artifacts/.aplh/formal_promotions_log.yaml`
- existing demo `.aplh/promotion_manifests/*.yaml`
- existing demo `.aplh/handoffs/`
- existing demo `.aplh/traces/`
- existing demo `.aplh/cleanup_log.yaml`

Phase 6 is not allowed to treat these files as baseline artifact truth.

### 4.5 `.aplh` Writes Explicitly Forbidden from Automatic Mutation

The following are frozen as **manual-only** or **out-of-scope for automatic writers**:

- `artifacts/.aplh/freeze_gate_status.yaml`
- `artifacts/examples/minimal_demo_set/.aplh/freeze_gate_status.yaml`
- any artifact YAML under formal or demo artifact directories
- any attempt to rewrite demo evidence bundles as formal truth
- any automatic promotion of `accepted_for_review`, `pending_manual_decision`, or `freeze-complete`

### 4.6 Why Governance Writes Do Not Equal Freeze Advancement

The planned Phase 6 governance records are intentionally reflective:

- `freeze_readiness_report.yaml` reports state; it does not grant freeze.
- `advisory_resolutions.yaml` records debt routing and closure evidence; it does not change artifact truth.
- `acceptance_audit_log.yaml` records intake and handoff; it does not approve freeze.

This distinction is frozen because Phase 6 must prepare human review, not replace it.

---

## 5. Core Objects and Deliverables

### 5.1 Deliverable A: `freeze_readiness_report.yaml`

Planned location:

- `artifacts/.aplh/freeze_readiness_report.yaml`

Minimum required contents:

- `report_id`
- `generated_at`
- `formal_baseline_dir`
- `source_demo_dir`
- `population_state`
- `validation_state`
- `review_preparation_state`
- `gate_results`
- `blocking_conditions`
- `advisory_status_refs`
- `manifest_refs`
- `promotion_audit_refs`
- `manual_actions_required`

This file is a machine-readable governance reflection. It does not declare freeze.

### 5.2 Deliverable B: `advisory_resolutions.yaml`

Planned location:

- `artifacts/.aplh/advisory_resolutions.yaml`

Minimum required contents per advisory:

- `advisory_id`
- `title`
- `phase6_subphase`
- `priority`
- `gate_id`
- `tier`
- `status`
- `resolution_rule`
- `evidence_refs`
- `notes`

This file is the formal routing home for ADV-1 through ADV-4.

### 5.3 Deliverable C: `acceptance_audit_log.yaml`

Planned location:

- `artifacts/.aplh/acceptance_audit_log.yaml`

Minimum required contents per entry:

- `timestamp`
- `actor`
- `action`
- `state_before`
- `state_after`
- `evidence_refs`
- `notes`

This log records review packet intake and review handoff milestones. It is not a freeze decision ledger.

### 5.4 Deliverable D: Phase 6 Prompt Skeleton

The official implementation skeleton is frozen in Section 11 of this document. No separate prompt file is required in this planning backfill.

---

## 6. Gate Design

Phase 6 gates are frozen as follows.

| Gate | Tier | Inputs | Check Items | Pass Condition | Failure Modes |
|---|---|---|---|---|---|
| `G6-A Population Classification` | T1 | formal artifact dirs, manifest refs, promotion audit log | Formal root contains only allowed promotion targets; promoted files are corroborated by manifest and audit records; Phase 2A artifact classes are present before `populated` is claimed | Formal state can be classified as `promoted` or `populated` without ambiguity | Files copied without corroborating manifest/log, missing artifact classes, ghost files in formal root |
| `G6-B Post-Validation Hard Gate` | T1 | formal root, `FormalPopulationChecker` outputs | Schema, trace, consistency, mode, and coverage results evaluated on current formal root | `post-validated` only if all applicable checks pass | Soft-passing invalid formal graph, schema failures hidden as advisory only |
| `G6-C Boundary and Advisory Hardening` | T1 | guardrail logic, reporting integration plan, tests | ADV-1, ADV-2, and ADV-4 closure criteria are met; ADV-3 integration path frozen | No unsafe path traversal, no soft `post-validated`, stronger boundary evidence in place | Path traversal still open, weak test coverage, report wiring still ambiguous |
| `G6-D Review Packet Assembly` | T1 | readiness report, advisory resolutions, manifests, promotion audit log, evidence bundle refs | Review packet is machine-readable, references are stable, `.aplh` writes are governance-only, no auto-edit to `freeze_gate_status.yaml` | `ready_for_freeze_review` can be claimed | Missing report, advisory routing absent, governance records treated as artifact truth |
| `G6-E Review Intake` | T2 | review packet plus manual acknowledgement | Human reviewer receives and acknowledges the packet, recorded in `acceptance_audit_log.yaml` | `accepted_for_review` or `pending_manual_decision` recorded | Packet exists but no accountable intake, review handoff not auditable |
| `G6-F Final Freeze Decision` | T3 | formal baseline, human review outcome, `freeze_gate_status.yaml` | Manual freeze decision only | `freeze-complete` may be written by a human reviewer | Any attempt to auto-advance freeze state, conflating readiness with freeze |

### 6.1 Tier Definitions

- `T1`: Programmatic hard gate. Must be machine-checkable and machine-enforced.
- `T2`: Hybrid gate. Requires machine-prepared evidence plus explicit human acknowledgement.
- `T3`: Human-only decision gate. Must never be auto-passed.

---

## 7. Development Order and Milestones

### 7.1 Milestone P6-M0: Planning Backfill

Deliverables:

- This document
- `docs/PHASE6_REREVIEW_INPUT.md`
- README state sync
- docs index sync

Exit condition:

- Independent reviewer has a real Phase 6 planning baseline to audit

### 7.2 Milestone P6-M1: State Classification Layer

Deliverables:

- Programmatic classification for `promoted`, `populated`, `post-validated`, `ready_for_freeze_review`
- Formal `freeze_readiness_report.yaml`

Entry condition:

- P6-M0 accepted

Exit condition:

- No ambiguity remains between physical copy, validated state, and review-ready state

### 7.3 Milestone P6-M2: Advisory Hardening and Governance Records

Deliverables:

- ADV-1 closure
- ADV-2 closure
- ADV-3 integration decision implemented
- ADV-4 stronger tests
- `advisory_resolutions.yaml`
- `.aplh` write boundary enforcement in implementation

Entry condition:

- P6-M1 implemented

Exit condition:

- Safety, validation, and reporting advisories are no longer open planning debt

### 7.4 Milestone P6-M3: Review Intake Preparation

Deliverables:

- `acceptance_audit_log.yaml`
- Review packet assembly path
- Manual review intake flow

Entry condition:

- P6-M2 implemented

Exit condition:

- Formal baseline can be handed to an independent freeze reviewer without implying freeze

### 7.5 Phase 6 Exit Condition

Phase 6 is complete only when the project can truthfully claim:

- formal baseline has been populated
- post-validation is hard-gated
- advisory routing is closed
- review packet is machine-readable and handoff-ready
- final freeze is still pending manual decision unless a separate human review says otherwise

---

## 8. Risk List

| Risk | Consequence | Mitigation |
|---|---|---|
| `promoted` / `populated` / `freeze-complete` are conflated again | Formal baseline may be treated as frozen without human decision | Freeze the state ladder and who may advance each state |
| `.aplh` governance records leak into source-of-truth status | Review metadata pollutes baseline artifact truth | Keep source-of-truth hierarchy explicit and forbid artifact facts inside governance writers |
| Guardrail traversal gap persists | Promotion path can escape approved directories | Route ADV-1 to a T1 hardening gate before further population work |
| Post-validation remains advisory-only | Invalid formal graph may still be treated as ready | Route ADV-2 to `G6-B` and freeze `post-validated` as hard only |
| Reporting integration remains partial | Review packet becomes non-authoritative and hard to audit | Route ADV-3 into Phase 6, freeze structured report expectations now |
| Historical docs continue to drift | Reviewers read stale status and nonexistent links | Add docs index and make current authoritative path explicit |

---

## 9. Technical Debt and Advisory Priorities

All four accepted advisory findings are formally routed into Phase 6.

| Advisory | Topic | Phase 6 Subphase | Priority | Gate | Tier | Why It Enters Phase 6 Now |
|---|---|---|---|---|---|---|
| `ADV-1` | Path traversal protection | `P6-M2` | P1 | `G6-C` | T1 | Formal population cannot proceed under a traversal hole, even if manifests are internally generated |
| `ADV-2` | Post-validation becomes hard gate | `P6-M1` then enforced in `P6-M2` | P1 | `G6-B` | T1 | Phase 6 is exactly where `post-validated` must be frozen as a real state, not a soft suggestion |
| `ADV-3` | `PromotionPlan` / `generate_report()` integration gap | `P6-M2` | P2 | `G6-D` | T2 | Review-preparation quality depends on a structured, authoritative report path rather than dead or bypassed models |
| `ADV-4` | Stronger boundary tests | `P6-M2` | P2 | `G6-C` | T1 | Phase 6 needs auditable proof that the tightened boundary and validation contracts are really enforced |

Priority rules are frozen as:

- `P1`: Must close before Phase 6 can claim `post-validated` or `ready_for_freeze_review`
- `P2`: Must close before Phase 6 implementation can be accepted
- No Phase 6 advisory is allowed to slide into Phase 7+

---

## 10. Relationship to `freeze-complete`

### 10.1 Frozen State Ladder

| State | Meaning | Does Not Mean | Entry Authority | Exit Authority | Auto-Advance Allowed |
|---|---|---|---|---|---|
| `promoted` | At least one approved manifest has been physically executed into the formal boundary and recorded in the promotion audit log | Not `populated`, not `post-validated`, not `freeze-complete` | Phase 5 executor plus audit logger | Phase 6 classifier | No silent advance; must be corroborated by logs |
| `populated` | Formal root now contains the required promoted artifact classes and evidence needed to evaluate the formal graph | Not validated, not review-ready, not frozen | Phase 6 T1 classifier/report | Phase 6 T1 validator | No human shortcut; classifier must derive it |
| `post-validated` | Current formal root passes all applicable static validation required by `G6-B` | Not review intake, not freeze approval | Phase 6 T1 validators only | Phase 6 review packet builder or later human review path | No manual override |
| `ready_for_freeze_review` | Formal root is populated, post-validated, advisory-routed, and review packet complete | Not `freeze-complete`, not human-accepted review outcome | Phase 6 T1 report builder | Human review intake | No automatic freeze advance |
| `accepted_for_review` | A responsible human has acknowledged the review packet and accepted it into the review queue | Not freeze approval, not signoff | Human reviewer or governance owner, recorded in `acceptance_audit_log.yaml` | Human reviewer | No automatic transition from machine report alone |
| `pending_manual_decision` | Manual review is active and waiting for explicit freeze decision | Not approved, not rejected, not freeze-complete | Human reviewer, recorded in `acceptance_audit_log.yaml` | Human reviewer | No auto-advance |
| `freeze-complete` | Formal baseline freeze is manually signed in `artifacts/.aplh/freeze_gate_status.yaml` | Not merely promoted/populated/validated/review-ready | Human freeze authority only | Human freeze authority only | Never auto |

### 10.2 Who May Not Advance States

The following prohibitions are frozen:

- `PromotionExecutor` may not set `populated`, `post-validated`, `ready_for_freeze_review`, or `freeze-complete`.
- `ReadinessAssessor` may not edit `freeze_gate_status.yaml`.
- Any `.aplh` writer may not infer or auto-write `freeze-complete`.
- No automated flow may bypass `accepted_for_review` / `pending_manual_decision` once the process enters human review.

### 10.3 Why `populated` Is Not `freeze-complete`

`populated` means files exist in the formal boundary. It does not mean:

- graph quality is acceptable
- validation has passed
- advisories are resolved
- a review packet exists
- a human has decided to freeze

That distinction is mandatory and remains frozen.

---

## 11. Phase 6 Implementation Prompt Skeleton

### 11.1 Recommended Session

- Session name: `APLH-Phase6-Exec`
- Primary model: `GPT-5.4`
- Fallback order: `GLM-5-Turbo` -> `Gemini 3.1 Pro`

### 11.2 Role Definition

You are the Phase 6 implementation executor.  
You are not the freeze approver.  
You are not allowed to widen scope into Phase 7/8+.

### 11.3 Single Goal

Implement the accepted Phase 6 architecture plan so that the repository can classify formal baseline state through `promoted -> populated -> post-validated -> ready_for_freeze_review`, while preserving all frozen boundaries from Phases 0-5.

### 11.4 Mandatory Inputs

- `docs/PHASE6_ARCHITECTURE_PLAN.md`
- `docs/PHASE5_REVIEW_REPORT.md`
- `docs/PHASE5_IMPLEMENTATION_NOTES.md`
- `aero_prop_logic_harness/services/readiness_assessor.py`
- `aero_prop_logic_harness/services/promotion_executor.py`
- `aero_prop_logic_harness/services/promotion_guardrail.py`
- `aero_prop_logic_harness/services/formal_population_checker.py`
- `aero_prop_logic_harness/services/promotion_manifest_manager.py`
- `aero_prop_logic_harness/services/promotion_audit_logger.py`
- `aero_prop_logic_harness/models/promotion.py`
- `aero_prop_logic_harness/models/freeze_status.py`

### 11.5 Boundaries

- Do not modify `freeze_gate_status.yaml` automatically.
- Do not declare `freeze-complete`.
- Do not reopen schema / trace / evaluator contracts.
- Do not introduce runtime platform features, dashboard, or certification packaging.
- Keep `ModeGraph`, validators, `GuardEvaluator`, and `RicherEvaluator` boundaries intact.
- Keep `TRANS.actions` and `Function.related_transitions` out of consistency-scope broadening unless a later accepted plan explicitly changes that.

### 11.6 Required Deliverables

- Formal state classification implementation
- Hard `post-validated` gate
- Advisory closures for ADV-1 through ADV-4
- Governance-only `.aplh` writers per this plan
- Tests proving boundary preservation and stronger evidence

### 11.7 Mandatory Gates

- `G6-A` through `G6-E` must be implemented and evidenced
- `G6-F` remains manual and out of automatic scope

### 11.8 Explicit Prohibitions

- No Phase 7/8 work
- No edits to accepted freeze contracts
- No auto-promotion of manual review state
- No auto-freeze

---

## 12. Final Recommendation

### 12.1 Immediate Next Step

Do **not** start implementation immediately from conversation memory.

The next step is:

- Session: `APLH-Phase6-Exec`
- Model: `GPT-5.4`
- Fallback: `GLM-5-Turbo` -> `Gemini 3.1 Pro`
- Responsibility: implement the accepted Phase 6 contract without widening scope
- Acceptance record: `docs/PHASE6_PLAN_REVIEW_REPORT.md`

### 12.2 Implementation Sequencing Recommendation

The project should proceed in this order:

1. Read the accepted planning review report
2. Implement against this planning baseline in a dedicated `APLH-Phase6-Exec` session
3. Submit implementation results to the next independent review gate before any later-phase work

### 12.3 Planning Judgment

The correct decision is:

- Planning accepted
- Execute next

Phase 6 must now execute only from the accepted repository-backed plan.
