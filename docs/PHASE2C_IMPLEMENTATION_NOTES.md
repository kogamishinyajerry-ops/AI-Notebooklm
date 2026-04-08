# APLH Phase 2C Implementation Notes

**Version:** 1.0.1
**Status:** Accepted — Independent Review Passed
**Date:** 2026-04-04
**Author:** Phase 2C Execution Session (Opus 4.6)
**Review:** Independent review completed 2026-04-04; 4 non-blocking items identified and addressed in Phase 3-1.

---

## 1. Overview

Phase 2C delivers the **Demo-scale Scenario Engine / Execution Readiness Layer** for APLH.
It safely operationalizes the static `ModeGraph` without polluting its topology, enabling scenario-based evaluation, strict predicate checking, and baseline-local Manual Signoffs (T2 Hooks).

### Key Deliverables
1. **Scenario Schema / Contract**: `Scenario` and `ScenarioTick` objects supporting strictly-sequenced test vectors.
2. **Runtime Container**: `RuntimeState` container operating structurally outside `ModeGraph`.
3. **Guard Evaluator**: Strict predicate interpreter bound to Pydantic definitions (NO general `eval()` / string formulas).
4. **Scenario Engine**: Single-tick state resolution, conflict blocking, and arbitration.
5. **Decision Trace**: Trace output formatting, strictly outputting `TRANS.actions` as emitted messages, avoiding `Execution Semantics` pollution.
6. **T2 Signoff Hooks**: `run-scenario` and `signoff-demo` CLI additions, restricting side effects strictly to `demo-scale`.

---

## 2. Architecture Decisions & Red Lines Maintained

- **ModeGraph is Unpolluted**: The graph is used identically to Phase 2B. No tracking variables (e.__.`is_active_mode`, `last_executed_tick`) were added to the `Mode` object.
- **`actions` remain Field-Only**: While the engine technically "fires" transitions, any `TRANS.actions` references simply echo into the execution trace string list without attempting callback resolution, thus maintaining the frozen rule.
- **Predicates remain Limited**: Guard filtering strictly handles `=, >, <, bool_true`, etc. Attempted expressions break immediately.
- **Only Demo Scale is Operable**: The CLI refuses to execute or signoff anything inside `artifacts/` (Formal Root). 2C remains a demo readiness architecture.

---

## 3. Files Created / Modified

| File | Status | Purpose |
|------|--------|---------|
| `aero_prop_logic_harness/models/scenario.py` | **NEW** | Defined Pydantic structure for scenarios |
| `aero_prop_logic_harness/services/guard_evaluator.py` | **NEW** | Operator lookup interpreter for signals against guards |
| `aero_prop_logic_harness/services/decision_tracer.py` | **NEW** | Collection queue for step-by-step history logs and events |
| `aero_prop_logic_harness/services/scenario_engine.py` | **NEW** | Main transition loop controller and Runtime state |
| `aero_prop_logic_harness/cli.py` | **MODIFIED** | Added `run-scenario` and `signoff-demo` CLI commands |
| `tests/test_phase2c.py` | **NEW** | Test suite covering 2C (engine conflicts, T2 logic etc.) |
| `docs/PHASE2C_IMPLEMENTATION_NOTES.md` | **NEW** | This document |

---

## 4. Test Results

Execution adds tests specifically targeting bounds compliance and expected logic blocking:

- **Guard Evaluator Misses**: Ensures an exception is correctly surfaced instead of defaulting to False when signals are absent (`test_guard_evaluator_missing_signal`).
- **Priority Conflict Blocked**: Proves T2 engine halting when equal-priority valid outward transitions race (`test_engine_priority_conflict`).
- **Degraded Recovery Blocked**: Halts the engine unconditionally when transitioning from degraded modes to non-normal modes (`test_engine_degraded_recovery`).
- **CLI Security Reject**: Unmanaged environment rejections when writing signoffs.

Result: 100% Passing (Total 162/162 project-wide).

---

## 5. What Was Explicitly Excluded (Out of Scope)

- **Scenario Authoring GUI / Mass Generators**: Scenarios must be supplied explicitly.
- **Trace Relationship from Transit Action to Event execution**: We log the `Action` IDs but we do not verify functional correctness of the function they map to.
- **Phase 3 Evaluator logic**: There are no control-response loops, integrals, or state diffs handled inside the Scenario Engine.
