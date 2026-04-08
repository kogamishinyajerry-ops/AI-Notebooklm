# Phase 4 Implementation Notes: Formal Readiness & Controlled Promotion

**Date:** 2026-04-05
**Engineer:** APLH-Phase4-Exec

## 1. Objective

Implement the "Formal Readiness / Controlled Promotion Path" layer on top of Phase 3-4 Demo-Scale Handoff. Goal is to prepare the mechanism for promoting demo-scale validated artifacts to the formal baseline, without actually modifying the formal baseline or changing the current `freeze_gate_status.yaml` states.

## 2. Technical Debt Closure (TD-P4-1, P4-2, P4-3)

- **TD-P4-1:** `evaluator_mode` metadata validation was originally heavily reliant on grepping trace files for terms like `HYSTERESIS_BAND` or `SUSTAINED`. We enhanced `DecisionTrace` to accept and serialize an explicit `evaluator_mode` metadata field natively. `ScenarioEngine` injects this directly during run time.
- **TD-P4-2:** The stateful operator advisory previously scanned traced `block_reason` fields. Now, `HandoffBuilder` correctly loads the `ArtifactRegistry` and statically inspects the parsed `Predicate` constructs of visited transitions, guaranteeing full visibility into stateful operators (like `sustained_gt`, `hysteresis_band`) irrespective of block reasons.
- **TD-P4-3:** Orphan traces (in-progress runs) previously generated scary `[Orphan Trace]` warnings in the handoff document, causing noise. `handoff_builder.py` was tweaked to display these as a non-fatal `*Advisory: In-Progress Runs Detected*`.

## 3. Core Delivery

- **Readiness Assessor:** Implemented `services/readiness_assessor.py`. Exposes the CLI command `assess-readiness`. It correctly verifies 6 core promotion prerequisites. Handles non-existent vs. empty `artifacts/` properly as `"not_met"`, ensuring 100% dry-run behaviour on the formal baseline.
- **Promotion Models:** Pydantic `extra="forbid"` models were introduced under `models/promotion.py`, strictly typing Candidate, Manifest, Blockers, and Readiness constructs.
- **Promotion Policy Checker:** `services/promotion_policy.py` introduces rigorous policy evaluations against Phase 2A+ limitations and checks for demo-scale signoff dependencies.
- **Evidence Checker:** `services/evidence_checker.py` implements a sandbox-based mechanism (using ephemeral `tempfile` structures) that tests candidate injections against `SchemaValidator`, `TraceValidator`, `ConsistencyValidator`, and `ModeValidator` simultaneously, strictly preventing writing to the original formal directory. Exposes the CLI command `check-promotion`.

## 4. Architectural Enforcement

- No usage of `eval()`, `exec()`, or modifications to existing Frozen Phase APIs (e.g. `scenario_engine`).
- `test_phase4.py` includes validation confirming that boundaries natively enforce strict dry-run behaviour (`Evidence checker wrote to formal baseline!` blocked). Validation for `VALID_TRACE_DIRECTIONS` remains unchanged at 25 rules.
- Fully local-first infrastructure with data structures matching YAML constraints.

## 5. Review-Round Fixes (2026-04-06)

The following fixes were applied after independent review identified 4 blocking issues:

- **P1 (Critical):** Replaced `art._path` access in `check-promotion` CLI with path reconstruction from the strict naming convention enforced by `artifact_loader.py`. Artifact Pydantic models never carry `_path`; paths are computed as `root_dir / {type_dir} / {id.lower()}.yaml`.
- **P2 (Boundary):** Moved promotion manifest output from `formal_dir/.aplh/promotion_manifests/` to `demo_dir/.aplh/promotion_manifests/`. Formal baseline is now guaranteed to never receive promotion manifest writes.
- **P3 (Fragility):** Removed hardcoded `"285 tests, all green"` from PRE-6 prerequisite. Now uses stable wording: `"Project test suite green in current validated environment"`.
- **P4 (Coverage):** Added 6 regression tests to `tests/test_phase4.py` (now 10 total): `_path` attribute absence, CLI crash regression on demo/formal paths, formal manifest zero-write, PRE-6 non-hardcoded wording.

All 295 tests pass. No frozen contracts or prior-phase behavior was modified.

## 6. Next Steps

Phase 4 architecture is now structurally implemented with review-round fixes applied. Pending re-review.
