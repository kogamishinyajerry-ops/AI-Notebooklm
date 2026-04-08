# Richer Evaluator Boundary (Phase 3-3)

**Version:** 1.0.0
**Date:** 2026-04-05
**Status:** Phase 3-3 Implemented — Pending Independent Review

---

## Overview

Phase 3-3 introduces a **RicherEvaluator** adapter that extends the 2C GuardEvaluator with 6 additional operators for demo-scale scenario evaluation.

### Architecture Constraint

The RicherEvaluator is an **outer adapter layer**. The `GuardEvaluator` core code is **never modified**. All richer operators live in the adapter layer:

```
RicherEvaluator (adapter)
├── Baseline operators (GT, GE, LT, LE, EQ, NE, BOOL_TRUE, BOOL_FALSE)
│   └── Delegated to GuardEvaluator unchanged
└── Richer operators (Phase 3-3)
    ├── DELTA_GT / DELTA_LT
    ├── IN_RANGE
    ├── SUSTAINED_GT / SUSTAINED_LT
    └── HYSTERESIS_BAND
```

State dependencies are read from `RuntimeState`, never from `ModeGraph` or validators.

---

## Operators

### DELTA_GT / DELTA_LT

Signal change between consecutive ticks.

| Field | Required | Description |
|-------|----------|-------------|
| `threshold` | Yes | Delta threshold (numeric) |
| `signal_ref` | Yes | Single signal reference (`IFACE-NNNN.signal_name`) |

**Semantics**:
- `DELTA_GT`: `current_value - previous_value > threshold`
- `DELTA_LT`: `current_value - previous_value < threshold`
- First tick (no previous snapshot): returns `False` (delta undefined)

**Example**:
```yaml
predicate:
  predicate_type: "atomic"
  operator: "delta_gt"
  signal_ref: "IFACE-0001.N1_Speed"
  threshold: 500.0
```

### IN_RANGE

Value within inclusive bounds `[threshold, threshold_high]`.

| Field | Required | Description |
|-------|----------|-------------|
| `threshold` | Yes | Lower bound (inclusive) |
| `threshold_high` | Yes | Upper bound (inclusive) |
| `signal_ref` | Yes | Single signal reference |

**Example**:
```yaml
predicate:
  predicate_type: "atomic"
  operator: "in_range"
  signal_ref: "IFACE-0001.N1_Speed"
  threshold: 2000.0
  threshold_high: 4800.0
```

### SUSTAINED_GT / SUSTAINED_LT

Value sustained above/below threshold for N consecutive ticks.

| Field | Required | Description |
|-------|----------|-------------|
| `threshold` | Yes | Comparison threshold |
| `duration_ticks` | Yes | Window length (1–100) |
| `signal_ref` | Yes | Single signal reference |

**Semantics**: Checks the last `duration_ticks` entries in signal history. Returns `False` if insufficient history.

**Example**:
```yaml
predicate:
  predicate_type: "atomic"
  operator: "sustained_gt"
  signal_ref: "IFACE-0001.N1_Speed"
  threshold: 5250.0
  duration_ticks: 3
```

### HYSTERESIS_BAND

Asymmetric threshold with state memory.

| Field | Required | Description |
|-------|----------|-------------|
| `threshold` | Yes | Lower band edge (exit threshold) |
| `threshold_high` | Yes | Upper band edge (enter threshold) |
| `signal_ref` | Yes | Single signal reference |

**Semantics**:
- Enter band (→ True): value exceeds `threshold_high`
- Exit band (→ False): value drops below `threshold`
- Between thresholds: maintains current state

**Example**:
```yaml
predicate:
  predicate_type: "atomic"
  operator: "hysteresis_band"
  signal_ref: "IFACE-0001.Oil_Pressure"
  threshold: 20.0
  threshold_high: 40.0
```

---

## Constraints

| Constraint | Value | Rationale |
|-----------|-------|-----------|
| `duration_ticks` max | 100 | Prevent unbounded memory growth |
| Richer operator count | Exactly 6 | Finite, auditable set |
| Cross-signal arithmetic | Prohibited | No PID/integral/derivative logic |
| `eval()` / `exec()` / `compile()` | Prohibited | No dynamic code execution |
| Missing signals | Raise `EvaluationError` | No silent fallback |
| `signal_ref` | Single string | One signal per atomic predicate |

---

## Explainability

Every evaluation produces a structured `RicherEvaluationResult`:

```python
@dataclass
class RicherEvaluationResult:
    value: bool                          # Evaluation result
    evaluator_mode: str                  # "baseline" or "richer"
    steps: List[EvaluationStep]          # Machine-readable explanation
    error: Optional[str] = None          # Error if any

@dataclass
class EvaluationStep:
    operator: str                        # e.g., "delta_gt"
    signal_ref: str                      # e.g., "IFACE-0001.N1_Speed"
    threshold: Optional[Any]             # Threshold value
    threshold_high: Optional[Any]        # Upper threshold (IN_RANGE, HYSTERESIS)
    duration_ticks: Optional[int]        # Window length (SUSTAINED)
    current_value: Optional[Any]         # Current signal value
    previous_value: Optional[Any]        # Previous tick value (DELTA)
    result: bool                         # Step result
    reason: str                          # Machine-readable explanation
```

---

## RuntimeState Extensions

Phase 3-3 adds three fields to `RuntimeState` (all backward compatible):

| Field | Type | Purpose |
|-------|------|---------|
| `signal_history` | `Dict[str, List[Any]]` | Rolling window per signal (SUSTAINED) |
| `previous_signal_snapshot` | `Dict[str, Any]` | Prior tick values (DELTA) |
| `hysteresis_state` | `Dict[str, bool]` | Per-signal boolean state (HYSTERESIS) |

These are populated by `ScenarioEngine` during tick processing when a `RicherEvaluator` is injected.

---

## CLI Usage

```bash
# Run scenario with richer evaluator:
python -m aero_prop_logic_harness run-scenario --dir artifacts/examples/minimal_demo_set \
  --scenario artifacts/examples/minimal_demo_set/scenarios/richer_delta_anomaly.yml \
  --richer

# Replay scenario with richer evaluator:
python -m aero_prop_logic_harness replay-scenario --dir artifacts/examples/minimal_demo_set \
  --scenario artifacts/examples/minimal_demo_set/scenarios/richer_delta_anomaly.yml \
  --trace .aplh/traces/run_RUN-XXXX.yaml \
  --richer
```

---

## Files

| File | Type | Purpose |
|------|------|---------|
| `services/richer_evaluator.py` | NEW | RicherEvaluator adapter with 6 operators + explainability |
| `models/predicate.py` | MODIFIED | Added 6 richer operators, `threshold_high`, `duration_ticks` |
| `services/scenario_engine.py` | MODIFIED | RuntimeState extensions + evaluator injection + history tracking |
| `services/replay_reader.py` | MODIFIED | evaluator parameter passthrough |
| `cli.py` | MODIFIED | `--richer` flag on run-scenario / replay-scenario |
| `tests/test_phase3_3.py` | NEW | 48 tests covering all operators + Gate P3-B + CLI |
| `docs/RICHER_EVALUATOR.md` | NEW | This document |

---

## Scope Exclusions

- General DSL / expression language platform
- Cross-signal arithmetic
- PID / integral / derivative logic
- `eval()` / `exec()` / `compile()`
- Formal baseline freeze
- Phase 3-4 (enhanced demo-scale handoff)
