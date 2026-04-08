# Phase 2A Implementation Notes — Handoff Document

**Document ID:** APLH-IMPL-2A  
**Version:** 1.0.0  
**Status:** Implementation Complete — Pending Independent Review  
**Implemented by:** Phase 2A Execution (Opus 4.6)  
**Date:** 2026-04-03  

---

## 1. What Was Implemented

### New Artifact Models

| Model | File | Extends | Key Authority Field |
|---|---|---|---|
| `Mode` | `models/mode.py` | `ArtifactBase` | `mode_type` (constrained enum) |
| `Transition` | `models/transition.py` | `ArtifactBase` | `source_mode`, `target_mode` |
| `Guard` | `models/guard.py` | `ArtifactBase` | `predicate` (sole machine authority) |

### Predicate Grammar

| Model | File | Discriminator |
|---|---|---|
| `AtomicPredicate` | `models/predicate.py` | `predicate_type: "atomic"` |
| `CompoundPredicate` | `models/predicate.py` | `predicate_type: "compound"` |

Grammar constraints enforced at load time:
- `signal_ref` must match `IFACE-NNNN.signal_name`
- Comparison operators (`gt`, `ge`, `lt`, `le`, `eq`, `ne`) require non-null threshold
- Boolean operators (`bool_true`, `bool_false`) require null threshold
- `NOT` takes exactly 1 operand; `AND`/`OR` take 2+
- Recursive nesting supported (CompoundPredicate can contain CompoundPredicate)

### P0/P1 Additive Fields (§2.6)

| Model | New Fields |
|---|---|
| `Requirement` | `linked_modes`, `linked_transitions`, `linked_guards` |
| `Function` | `related_modes`, `related_transitions` |
| `Interface` | `related_modes`, `related_guards` |
| `Abnormal` | `related_modes`, `related_transitions` |

All fields: `list[str] = []`, additive-only, backward compatible.

### Reciprocal Fields (§2.7)

| Model | Reciprocal Field |
|---|---|
| `Mode` | `incoming_transitions`, `outgoing_transitions` |
| `Guard` | `used_by_transitions` |

### Trace Extension

11 new `VALID_TRACE_DIRECTIONS` tuples added:

| # | Source | Target | Link Type |
|---|---|---|---|
| 1 | REQ | MODE | `requires_mode` |
| 2 | REQ | TRANS | `requires_transition` |
| 3 | REQ | GUARD | `defines_condition` |
| 4 | ABN | MODE | `triggers_mode` |
| 5 | ABN | TRANS | `triggers_transition` |
| 6 | MODE | FUNC | `activates` |
| 7 | MODE | IFACE | `monitors` |
| 8 | TRANS | MODE | `exits` |
| 9 | TRANS | MODE | `enters` |
| 10 | TRANS | GUARD | `guarded_by` |
| 11 | GUARD | IFACE | `observes` |

Explicitly blocked: `TRANS → FUNC` (§4.8), `TRANS → IFACE` (§4.6).

### Infrastructure

- `ID_PATTERN` extended: `MODE-`, `TRANS-`, `GUARD-` prefixes
- `ArtifactType` enum: `MODE`, `TRANSITION`, `GUARD`
- `artifact_loader.py`: new model class mapping + directory mapping
- `dump_schemas.py`: exports 9 schemas (6 existing + 3 new)
- Templates: `mode.template.yaml`, `transition.template.yaml`, `guard.template.yaml`

---

## 2. What Was NOT Implemented (Phase 2B+ Scope)

- **Graph engine** (`mode_graph.py`) — Phase 2B
- **Richer validators** (`mode_validator.py`, coverage checks) — Phase 2B
- **ConsistencyValidator extension** for reverse-loop on Phase 2 types — Phase 2B
- **New CLI commands** (`validate-modes`) — Phase 2B
- **Demo artifact authoring** — Phase 2C
- **Predicate evaluator / executor** — Phase 3+
- **No `TRANS ↔ FUNC` trace direction** — frozen field-only decision
- **No `TRANS ↔ IFACE` trace direction** — frozen field-only decision

---

## 3. Frozen Decisions Honored

| Decision | Source | Status |
|---|---|---|
| `predicate` is sole machine authority | §4.7 R3 freeze | ✅ Honored |
| `predicate_expression` must not exist | §4.7 R3 freeze | ✅ Honored (not a field) |
| `GUARD.description` is human-only | §4.7 R3 freeze | ✅ Honored |
| `TRANS.actions` is field-only | §4.8 freeze | ✅ Honored |
| No `TRANS → FUNC` trace | §4.8 freeze | ✅ Honored |
| No `TRANS → IFACE` trace | §4.6 freeze | ✅ Honored |
| demo-scale ≠ formal baseline | §1.2 / v4.1 | ✅ Unmodified |
| `.aplh/` is control metadata only | path_constants.py | ✅ Unmodified |

---

## 4. Test Coverage

111 tests total (30 existing + 81 new), all passing.

### New Test Classes

| Class | Coverage |
|---|---|
| `TestModeModel` | MODE schema ±, mode_type validation, extra fields |
| `TestTransitionModel` | TRANS schema ±, priority bounds, extra fields |
| `TestPredicateGrammar` | Atomic/Compound ±, threshold consistency, signal_ref, nesting, operand counts |
| `TestGuardModel` | GUARD schema ±, free-text rejection, `predicate_expression` rejection |
| `TestAdditiveFieldsBackwardCompat` | All 4 P0/P1 models with/without new fields |
| `TestTraceExtension` | All 11 new + all 14 old directions, TRANS→FUNC/IFACE rejection |
| `TestLoaderIntegration` | YAML load, registry, type spoofing |
| `TestP0P1Regression` | Demo set load, validate-artifacts CLI |
| `TestFieldOnlyBoundaries` | actions field-only, no predicate_expression |
| `TestNewIdPatterns` | MODE/TRANS/GUARD ID acceptance, malformed rejection |

---

## 5. Verification Commands & Results

| # | Command | Exit Code |
|---|---|---|
| 1 | `python -m pytest` | 0 (111 passed) |
| 2 | `python -m aero_prop_logic_harness validate-artifacts --dir artifacts/examples/minimal_demo_set` | 0 |
| 3 | `python scripts/dump_schemas.py` | 0 (9 schemas dumped) |

---

## 6. Entry Conditions for Phase 2B

Phase 2B may begin after this document passes independent review. Phase 2B scope includes:

1. **ConsistencyValidator extension**: `_get_all_embedded_links()` must handle MODE/TRANS/GUARD + §2.6 additive fields + §2.7 reciprocal fields
2. **Mode graph construction**: Build directed graph from MODE/TRANS artifacts
3. **Structural validators**: Reachability, deadlock detection, completeness
4. **Gate P2-B check items**: All 5 items must pass programmatically (T1)

Phase 2B must NOT modify any Phase 2A model schemas. Phase 2A schemas are now the contract.

---

## 7. Files Changed

### New Files (8)

| File | Purpose |
|---|---|
| `aero_prop_logic_harness/models/predicate.py` | Predicate grammar sub-models |
| `aero_prop_logic_harness/models/mode.py` | Mode artifact model |
| `aero_prop_logic_harness/models/transition.py` | Transition artifact model |
| `aero_prop_logic_harness/models/guard.py` | Guard artifact model |
| `templates/mode.template.yaml` | Mode YAML template |
| `templates/transition.template.yaml` | Transition YAML template |
| `templates/guard.template.yaml` | Guard YAML template |
| `tests/test_phase2a_models.py` | Phase 2A test suite (81 tests) |

### Modified Files (8)

| File | Change |
|---|---|
| `aero_prop_logic_harness/models/common.py` | Extended ArtifactType, ID_PATTERN, PREFIX_TO_TYPE |
| `aero_prop_logic_harness/models/requirement.py` | Added linked_modes/transitions/guards |
| `aero_prop_logic_harness/models/function.py` | Added related_modes/transitions |
| `aero_prop_logic_harness/models/interface.py` | Added related_modes/guards |
| `aero_prop_logic_harness/models/abnormal.py` | Added related_modes/transitions |
| `aero_prop_logic_harness/models/trace.py` | Extended TraceLinkType + VALID_TRACE_DIRECTIONS |
| `aero_prop_logic_harness/models/__init__.py` | Exported new types |
| `aero_prop_logic_harness/loaders/artifact_loader.py` | Added model/directory mappings |

### Updated Docs & Infrastructure (3)

| File | Change |
|---|---|
| `scripts/dump_schemas.py` | Added Mode/Transition/Guard schema dumps |
| `docs/ARTIFACT_MODEL.md` | Added Phase 2A types, updated extension points |
| `README.md` | Updated phase status, directory structure |

---

*Phase 2A implementation complete. Awaiting independent review.*
