# Phase 3 Implementation Notes

**Document ID:** APLH-IMPL-P3
**Version:** 0.4.0 (Phase 3-4 complete)
**Date:** 2026-04-05
**Status:** Phase 3-4 Implemented — Pending Independent Review

---

## Phase 3-1: Technical Debt Closure + Audit Identity

**Status:** Accepted (v0.1.0, 2026-04-04)

Deliverables:
1. `test_signoff_formal_rejected` replaced with real assertions (monkeypatch-based)
2. `README.md` Phase Status updated to 2C Accepted
3. `signoff-demo` `--reviewer` parameter added (no longer hardcoded)
4. `run_id` generation (`RUN-{uuid.hex[:12].upper()}`) in ScenarioEngine
5. `scenario_id` / `run_id` propagated through DecisionTrace and TransitionRecord
6. `models/signoff.py` — SignoffEntry Pydantic schema with `extra="forbid"`, ISO 8601 validation, `baseline_scope: Literal["demo-scale"]`

Technical debts closed: TD-1, TD-2, TD-3, TD-4.
Test count: 187 passed (162 pre-3-1 + 25 new).

---

## Phase 3-2: Scenario / Replay / Audit Strengthening

**Status:** Implemented — Pending Independent Review (v0.2.0, 2026-04-05)

### New Files

| File | Type | Purpose |
|------|------|---------|
| `services/scenario_validator.py` | NEW | Scenario structural pre-check (SV-1 through SV-6) |
| `services/replay_reader.py` | NEW | Trace persistence, readback, deterministic replay comparison |
| `templates/scenario.template.yml` | NEW | Scenario authoring template |
| `scenarios/normal_operation.yml` | NEW | Demo scenario: normal steady-state |
| `scenarios/degraded_entry.yml` | NEW | Demo scenario: degraded mode entry |
| `scenarios/emergency_shutdown.yml` | NEW | Demo scenario: emergency shutdown |
| `tests/test_phase3_2.py` | NEW | 43 tests for all 3-2 deliverables |
| `docs/PHASE3_IMPLEMENTATION_NOTES.md` | NEW | This document |

### Modified Files

| File | Change |
|------|--------|
| `models/scenario.py` | Added 3 optional fields: `version`, `expected_final_mode`, `expected_transitions` (backward compatible) |
| `cli.py` | Added 3 commands: `validate-scenario`, `replay-scenario`, `inspect-run`; added trace persistence to `run-scenario` |
| `README.md` | Updated Phase Status to reflect 3-1 Accepted + 3-2 Implemented; added CLI documentation for new commands |

### Architecture Decisions

1. **ScenarioValidator is structural only** — validates against ModeGraph topology, does NOT execute scenarios or evaluate guards. Six checks (SV-1 through SV-6) per §6.1.2 of the Phase 3 architecture plan.

2. **ReplayReader is NOT a second engine** — for deterministic comparison, it delegates re-execution to the existing ScenarioEngine. The replay layer only orchestrates comparison and provides readback.

3. **Trace persistence uses `.aplh/traces/`** — per §6.2.2 of the architecture plan. File naming: `run_{run_id}_{scenario_id}_{timestamp}.yaml`. Only written for demo-scale baselines.

4. **Scenario model additions are all Optional** — `version`, `expected_final_mode`, `expected_transitions` all default to `None`. Existing scenario files load without modification.

5. **All new CLI commands enforce demo/formal/unmanaged boundary** — formal directories are rejected with exit code 1 for validate-scenario, replay-scenario, and inspect-run.

6. **inspect-run includes signoff correlation** — reads `.aplh/review_signoffs.yaml` to find signoff entries matching the run_id, closing the audit correlation chain.

### Scope Exclusions (Not in 3-2)

- Richer evaluator boundary (Phase 3-3)
- AuditCorrelator class (Phase 3-4)
- Formal baseline freeze
- Production runtime
- GUI / authoring studio

### Frozen Contract Preservation (Gate P3-A)

- ModeGraph: no `step/fire/evaluate/execute` methods added
- GuardEvaluator: core code unchanged
- No TRANS→FUNC or TRANS→IFACE trace directions introduced
- VALID_TRACE_DIRECTIONS count unchanged at 25
- SignoffEntry schema from 3-1 preserved
- `predicate_expression` not reintroduced
- TRANS.actions remains field-only

### Test Results

- Pre-3-2 baseline: 187 passed
- Post-3-2: 230 passed (187 + 43 new)
- Zero regressions

---

## Phase 3-3: Richer Evaluator Boundary

**Status:** Implemented — Pending Independent Review (v0.3.0, 2026-04-05)

### New Files

| File | Type | Purpose |
|------|------|---------|
| `services/richer_evaluator.py` | NEW | Outer adapter with 6 richer operators + structured explainability |
| `tests/test_phase3_3.py` | NEW | 48 tests: operator evaluation, boundary gates, CLI integration |
| `docs/RICHER_EVALUATOR.md` | NEW | Richer evaluator operator reference |

### Modified Files

| File | Change |
|------|--------|
| `models/predicate.py` | Added 6 richer operators (DELTA_GT, DELTA_LT, IN_RANGE, SUSTAINED_GT, SUSTAINED_LT, HYSTERESIS_BAND), `threshold_high`, `duration_ticks` fields, operator set constants, hard cap on `duration_ticks` (max 100) |
| `services/scenario_engine.py` | RuntimeState extended with `signal_history`, `previous_signal_snapshot`, `hysteresis_state`; evaluator injection via constructor; history tracking during tick processing |
| `services/replay_reader.py` | `evaluator` parameter passthrough for replay consistency |
| `cli.py` | Added `--richer` flag to `run-scenario` and `replay-scenario` commands |
| `artifacts/examples/minimal_demo_set/` | Fixed cross-reference consistency (10 trace link bidirectional references) |

### Architecture Decisions

1. **RicherEvaluator is an outer adapter** — delegates baseline operators (GT, GE, LT, LE, EQ, NE, BOOL_*) to the **unchanged** GuardEvaluator core. All richer operators are handled in the adapter layer. GuardEvaluator source code is never modified.

2. **State lives in RuntimeState** — `signal_history`, `previous_signal_snapshot`, `hysteresis_state` are fields on RuntimeState, populated by ScenarioEngine during tick processing. RicherEvaluator reads these but does not own them (except HYSTERESIS_BAND which updates state as a side effect).

3. **Explicit evaluator injection** — ScenarioEngine accepts an optional `evaluator` parameter. Without it, behavior is identical to Phase 2C (baseline GuardEvaluator only). With it, the injected evaluator handles all operator types.

4. **6 richer operators, no more** — The operator set is finite and auditable: DELTA_GT, DELTA_LT, IN_RANGE, SUSTAINED_GT, SUSTAINED_LT, HYSTERESIS_BAND. Cross-signal arithmetic, PID, integral, derivative logic are all prohibited.

5. **Structured explainability** — Every evaluation produces a `RicherEvaluationResult` with machine-readable `EvaluationStep` records. No freeform string concatenation.

6. **Demo baseline cross-refs fixed** — 10 bidirectional trace link consistency errors in the demo baseline were resolved by adding missing embedded cross-reference fields to artifact YAML files.

### Operator Summary

| Operator | Type | Dependencies |
|----------|------|-------------|
| DELTA_GT | Signal change > threshold | `previous_signal_snapshot` |
| DELTA_LT | Signal change < threshold | `previous_signal_snapshot` |
| IN_RANGE | Value in [low, high] | `signal_snapshot` only |
| SUSTAINED_GT | All values in window > threshold | `signal_history` |
| SUSTAINED_LT | All values in window < threshold | `signal_history` |
| HYSTERESIS_BAND | Asymmetric threshold with memory | `signal_snapshot` + `hysteresis_state` |

### Scope Exclusions (Not in 3-3)

- General DSL / expression language platform
- Cross-signal arithmetic
- PID / integral / derivative logic
- eval() / exec() / compile()
- Formal baseline freeze
- Phase 3-4 (enhanced demo-scale handoff)

### Frozen Contract Preservation (Gate P3-B)

- GuardEvaluator: core code **unchanged**
- ModeGraph: no `step/fire/evaluate/execute` methods added
- No TRANS→FUNC or TRANS→IFACE trace directions introduced
- VALID_TRACE_DIRECTIONS count unchanged at 25
- `predicate_expression` not reintroduced
- TRANS.actions remains field-only
- All 2A/2B/2C/3-1/3-2 tests pass without regression

### Test Results

- Pre-3-3 baseline: 230 passed
- Post-3-3: 278 passed (230 + 48 new)
- Zero regressions

---

## Phase 3-4: Enhanced Demo-Scale Handoff

**Status:** Implemented — Pending Independent Review (v0.4.0, 2026-04-05)

### New Files

| File | Type | Purpose |
|------|------|---------|
| `services/hygiene_manager.py` | NEW | Manages explicit removal of legacy signoffs and orphan traces (P3D-A, P3D-B) |
| `services/audit_correlator.py` | NEW | Map `run_id` to traces, signoffs, and scenarios to ensure bundle chain integrity (P3D-C) |
| `services/handoff_builder.py` | NEW | Assembles point-in-time snapshot, runs validations, and generates report artifacts (P3D-D, P3D-E) |
| `tests/test_phase3_4.py` | NEW | Over 12 tests verifying hygiene bounds, correlation consistency, and CLI builder error handling |

### Modified Files

| File | Change |
|------|--------|
| `cli.py` | Added `clean-baseline` and `build-handoff` commands, enforcing strict environment checks (demo-scale only) |
| `README.md` | Updated Phase Status to reflect 3-4 Implemented; added command references |
| `docs/PHASE3_IMPLEMENTATION_NOTES.md` | New section for Phase 3-4 (this table) |

### Architecture Decisions

1. **Baseline Hygiene enforces manual action** — `clean-baseline` explicitly requires `--dry-run` or `--prune`. It identifies legacy (missing IDs) or demo/stub reviewers and removes them while persisting a `cleanup_log.yaml`.
2. **Audit Correlator in-memory strictness** — Builds a bidirectional mapping from `traces` and `signoffs`. Valid bundles only consist of fully intact chains (`Trace` <-> `Signoff(s)`).
3. **Handoff Builder defines Snapshot structure** — Bundles trace artifacts, exact scenarios, and signoffs locally into `.aplh/handoffs/BUNDLE_{DATETIME}/`. The report provides the P3D-E validation summary and directly invokes core P0/Phase 2 checks (`SchemaValidator`, `TraceValidator`, `ModeValidator`, etc.) to embed the results.
4. **Hysteresis advisory implemented** — The `index.yaml` and `report.md` clearly identify if any grouped scenarios utilized richer evaluation operators that mutate internal `RuntimeState` (e.g. `HYSTERESIS_BAND`).
5. **No Level-1 Modification** — At no point does the `HandoffBuilder` rewrite, mutate, or merge actual scenario contents. It simply creates an immutable point-in-time Level-2/3 reflection. Formal freeze gate still checks against Level-0 `artifacts/`.

### Scope Exclusions (Not in 3-4)

- Uploading bundles directly to external web endpoints (delegated to Phase 4).
- Formal Baseline modifications or freezing.
- Product deployment or auto-commit of the `review_signoffs.yaml`.

### Frozen Contract Preservation (Gate P3-F)

- No changes to ModeGraph logic or existing evaluation systems.
- Zero modifications to Phase 2C trace definitions, trans/guard semantics.
- Level-0 baseline remains inherently offline and directory-managed.

### Test Results

- Pre-3-4 baseline: 278 passed
- Post-3-4: 285 passed (278 + 7 new)
- Zero regressions
