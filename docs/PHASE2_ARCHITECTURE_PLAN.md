# APLH Phase 2 Architecture Planning Package

**Document ID:** APLH-ARCH-003
**Version:** 0.3.0-revised-R3
**Status:** PLANNING — Not yet approved for implementation
**Authored by:** Phase 2 Planning Session (Opus 4.6)
**Revised by:** Phase 2 Plan Revision R1 (Opus 4.6) — closes 5 structural gaps; R2 (Opus 4.6) — closes 4 remaining structural gaps; R3 (Opus 4.6) — closes 3 final field-naming/gate-tier/scope gaps
**Date:** 2026-04-03

---

## 1. Overall Conclusion

### 1.1 Is Phase 2 planning permitted now?

**Yes.** The P0/P1 control surface has reached Freeze Candidate status. The gate infrastructure is trustworthy (v4.1 closure patch confirmed: formal/demo boundary is programmatically enforced, CLI artifact views are unified, and integration tests pin both gaps). Planning and schema design for Phase 2 may proceed.

### 1.2 What must NOT be assumed

The following assumptions are explicitly prohibited:

1. **The formal `artifacts/` root is NOT freeze-complete.** Its `.aplh/freeze_gate_status.yaml` has all booleans set to `false`. Running `freeze-readiness --dir artifacts` returns exit 1 with empty graph and incomplete checklist failures. (Evidence: `artifacts/.aplh/freeze_gate_status.yaml` lines 2-5.)
2. **The demo set is NOT a formal baseline.** `artifacts/examples/minimal_demo_set` carries `baseline_scope: "demo-scale"` and the CLI enforces this programmatically via `path_constants.is_formal_baseline_root()`. (Evidence: `path_constants.py` line 40-42, `cli.py` line 218-226.)
3. **Phase 2 implementation is NOT complete.** This document is a planning deliverable only.
4. **Phase 2 cannot depend on formal baseline content existing.** All Phase 2 development must be viable against demo-scale inputs until formal baseline is populated and frozen.

---

## 2. Phase 2 Definition

### 2.1 Goal

Build a **reviewable, traceable, validatable state/mode logic layer** on top of the existing REQ/FUNC/IFACE/ABN/TRACE knowledge base. This layer must capture:

- Operating modes and their hierarchical structure (e.g., Normal, Degraded, Emergency)
- State transitions with explicit trigger conditions and guard predicates
- Actions bound to transitions and states (entry/exit/during behaviors)
- Abnormal entry paths, degradation cascades, and recovery conditions
- Priority arbitration when multiple transitions compete
- Extension points for future verification, simulation, and change-impact analysis

### 2.2 Non-goals (Out of Scope)

| Excluded item | Why excluded |
|---|---|
| Certified airborne software (DO-178C target code) | APLH is tooling, not target software (SYSTEM_SCOPE.md §3) |
| Executable control code generation | Phase 3+ at earliest; requires stable formal baseline |
| Real-time simulation / solver | Phase 3+; needs validated state models first |
| Airworthiness compliance evidence | APLH supports preparation, is not evidence itself |
| UI dashboard / visual editor | Phase 3+ (SYSTEM_SCOPE.md §6 Phase Scope Matrix) |
| Database backend | Local-first file principle (ASSUMPTIONS_AND_BOUNDARIES.md A3.3) |
| Multi-user concurrency | Single-user assumption still holds (A4.1) |
| Formal baseline population | Separate activity; Phase 2 must work without it |

### 2.3 Why only "planning + minimal implementation preparation" now

Three hard constraints:

1. **Formal baseline is empty.** `artifacts/` root contains zero engineering artifacts (0 traces, 0 requirements). Phase 2 execution harness would have nothing formal to execute against.
2. **Schema stability assumption.** HANDOFF_PHASE0_PHASE1.md §4 explicitly says "Do not modify the Phase 1 schema unless absolutely necessary." New artifact types must be additive, not breaking.
3. **Gate integrity.** The v4.1 closure patch just stabilized the P0/P1 control surface. Rushing into Phase 2 implementation before this planning is reviewed risks re-opening the very gaps that were just closed.

### 2.4 P0/P1 capabilities directly reusable by Phase 2

| P0/P1 asset | Phase 2 reuse |
|---|---|
| `ArtifactBase` (common.py) | New artifact types (MODE, TRANS, etc.) extend this base — inheriting `id`, `provenance`, `review_status`, `tags`, lifecycle states |
| `ArtifactType` enum + `PREFIX_TO_TYPE` map | Extend with new prefixes (MODE-, TRANS-, GUARD-) |
| `ID_PATTERN` regex | Extend to accept new prefixes |
| `TraceLinkType` enum + `VALID_TRACE_DIRECTIONS` set | Extend with new valid (source, target, link_type) triples |
| `ArtifactRegistry` | Extend `_add_item()` to handle new types; existing graph indexing works |
| `iter_artifact_yamls()` in `path_constants.py` | Shared traversal already excludes `.aplh/`; new artifact directories are auto-discovered |
| `SchemaValidator` | Works on any `load_artifact()`-compatible file; no changes needed |
| `ConsistencyValidator` | Extend `_get_all_embedded_links()` for new types |
| `freeze-readiness` CLI | Demo-scale vs formal boundary enforcement transfers directly |
| `FreezeGateStatus` model | Reuse for Phase 2 gate signoff records |

### 2.5 P0/P1 limitations that constrain Phase 2

| Limitation | Impact on Phase 2 | Evidence |
|---|---|---|
| `ID_PATTERN` is hardcoded to 6 prefixes | Must be extended before new artifacts can load | `common.py` line 76 |
| `VALID_TRACE_DIRECTIONS` is a fixed set of 14 tuples | Must be extended for new artifact-type pairs | `trace.py` lines 33-48 |
| `load_artifacts_from_dir()` depends on `PREFIX_TO_DIRECTORY` map in `artifact_loader.py` | Must add new prefix→directory entries | `artifact_loader.py` lines 67-74 |
| `_get_model_class()` maps 6 artifact types | Must register new model classes | `artifact_loader.py` lines 27-37 |
| `ConsistencyValidator._get_all_embedded_links()` only knows REQ/FUNC/IFACE/ABN | Must add cases for new types | `consistency_validator.py` lines 44-62 |
| `freeze-readiness` relational coverage check is hardcoded to 5 relations | Phase 2 will need its own coverage checks, not overloading P0/P1 gate | `cli.py` lines 147-170 |
| Demo set has 11 artifacts + 11 traces covering overspeed protection only | Phase 2 demo must extend or parallel this, not modify it | `artifacts/examples/minimal_demo_set/` |

### 2.6 Additive fields on P0/P1 models (Reverse-Loop Consistency)

**Problem:** `ConsistencyValidator._validate_trace_reverse_loop()` requires both endpoints of a TraceLink to acknowledge each other in embedded `linked_*`/`related_*` fields. The existing REQ/FUNC/IFACE/ABN models have NO fields referencing MODE/TRANS/GUARD. Without additive fields, any cross-generation TraceLink (e.g., `REQ → MODE`) will fail reverse-loop validation.

**Decision:** Phase 2A MUST add the following optional `list[str]` fields (default `[]`) to each P0/P1 model. These are additive-only changes — no existing field is modified or removed. `extra="forbid"` on Pydantic `ConfigDict` ensures no undeclared fields sneak in, so these MUST be declared in the model class.

| Model | New field | Referenced type | Trace direction it supports |
|---|---|---|---|
| `Requirement` | `linked_modes: list[str] = []` | MODE-xxxx | `(REQ, MODE, requires_mode)` |
| `Requirement` | `linked_transitions: list[str] = []` | TRANS-xxxx | `(REQ, TRANS, requires_transition)` |
| `Requirement` | `linked_guards: list[str] = []` | GUARD-xxxx | `(REQ, GUARD, defines_condition)` |
| `Function` | `related_modes: list[str] = []` | MODE-xxxx | `(MODE, FUNC, activates)` — reverse side |
| `Function` | `related_transitions: list[str] = []` | TRANS-xxxx | TRANS.actions reverse side |
| `Interface` | `related_modes: list[str] = []` | MODE-xxxx | `(MODE, IFACE, monitors)` — reverse side |
| `Interface` | `related_guards: list[str] = []` | GUARD-xxxx | `(GUARD, IFACE, observes)` — reverse side |
| `Abnormal` | `related_modes: list[str] = []` | MODE-xxxx | `(ABN, MODE, triggers_mode)` |
| `Abnormal` | `related_transitions: list[str] = []` | TRANS-xxxx | `(ABN, TRANS, triggers_transition)` |

**Backward compatibility:** All new fields default to `[]`. Existing YAML artifacts that lack these fields will load without error (Pydantic fills defaults). Existing tests will not break.

**Validator impact:** `ConsistencyValidator._get_all_embedded_links()` MUST be extended in Phase 2B to extract these new fields for reverse-loop checking.

**Schema migration:** No migration needed. Existing artifacts are valid as-is (empty list = no links). New fields only become populated when cross-generation traces are authored.

### 2.7 Reciprocal fields on NEW models (MODE, TRANS, GUARD) — Reverse-Loop Completeness

**Problem:** §2.6 freezes additive fields on P0/P1 models (the "old side"), but the new MODE and GUARD models themselves must also carry reciprocal fields to acknowledge TRANS — the artifact that references them via `source_mode`, `target_mode`, and `guard`. Without these fields, `_validate_trace_reverse_loop()` cannot confirm that both endpoints of a `(TRANS, MODE, exits/enters)` or `(TRANS, GUARD, guarded_by)` trace acknowledge each other.

**Decision:** The following reciprocal fields are frozen into the new artifact schemas. All are `list[str]`, default `[]`, additive, and validated by `ConsistencyValidator` in Phase 2B (P2-E5).

#### MODE reciprocal fields

| Field | Type | Referenced type | Acknowledges trace direction | Rationale |
|---|---|---|---|---|
| `incoming_transitions` | `list[str] = []` | TRANS-xxxx | `(TRANS, MODE, enters)` — reverse side | MODE must know which transitions can enter it, for reverse-loop to confirm TRANS.target_mode ↔ MODE.incoming_transitions |
| `outgoing_transitions` | `list[str] = []` | TRANS-xxxx | `(TRANS, MODE, exits)` — reverse side | MODE must know which transitions can exit it, for reverse-loop to confirm TRANS.source_mode ↔ MODE.outgoing_transitions |

**Why only transitions, not guards?** MODE does not directly reference GUARD. The path is MODE ← TRANS → GUARD. No trace direction connects MODE to GUARD directly, so no reciprocal field is needed between them. This avoids introducing an indirect coupling that would require triple-hop consistency checking.

#### GUARD reciprocal fields

| Field | Type | Referenced type | Acknowledges trace direction | Rationale |
|---|---|---|---|---|
| `used_by_transitions` | `list[str] = []` | TRANS-xxxx | `(TRANS, GUARD, guarded_by)` — reverse side | GUARD must know which transitions depend on it, for reverse-loop to confirm TRANS.guard ↔ GUARD.used_by_transitions |

**Why not `observed_interfaces` as a reciprocal?** GUARD already has `related_interfaces: list[str]` in its minimum field set (§4.3). This field ALREADY serves as the reciprocal acknowledgment for `(GUARD, IFACE, observes)`. No additional field is needed — `related_interfaces` is the reciprocal. Similarly, `related_requirements` acknowledges `(REQ, GUARD, defines_condition)`.

#### TRANS embedded links for reverse-loop extraction

TRANS has the following fields that serve as embedded links (to be extracted by `_get_all_embedded_links()` in Phase 2B):

| Field | Type | Target type | Trace direction |
|---|---|---|---|
| `source_mode` | `str` | MODE-xxxx | `(TRANS, MODE, exits)` |
| `target_mode` | `str` | MODE-xxxx | `(TRANS, MODE, enters)` |
| `guard` | `str` | GUARD-xxxx | `(TRANS, GUARD, guarded_by)` |
| `related_requirements` | `list[str]` | REQ-xxxx | `(REQ, TRANS, requires_transition)` — reverse side |
| `related_abnormals` | `list[str]` | ABN-xxxx | `(ABN, TRANS, triggers_transition)` — reverse side |

Note: `TRANS.actions` is explicitly **excluded** from consistency scope — see §4.8.

#### Complete reverse-loop coverage matrix

The table below shows every Phase 2 trace direction and which fields on each side satisfy the reverse-loop requirement:

| Trace direction | Source-side embedded field | Target-side reciprocal field |
|---|---|---|
| `(REQ, MODE, requires_mode)` | `Requirement.linked_modes` (§2.6) | `MODE.related_requirements` (§4.1) |
| `(REQ, TRANS, requires_transition)` | `Requirement.linked_transitions` (§2.6) | `TRANS.related_requirements` (§4.2) |
| `(REQ, GUARD, defines_condition)` | `Requirement.linked_guards` (§2.6) | `GUARD.related_requirements` (§4.3) |
| `(ABN, MODE, triggers_mode)` | `Abnormal.related_modes` (§2.6) | `MODE.related_abnormals` (§4.1) |
| `(ABN, TRANS, triggers_transition)` | `Abnormal.related_transitions` (§2.6) | `TRANS.related_abnormals` (§4.2) |
| `(MODE, FUNC, activates)` | `MODE.active_functions` (§4.1) | `Function.related_modes` (§2.6) |
| `(MODE, IFACE, monitors)` | `MODE.monitored_interfaces` (§4.1) | `Interface.related_modes` (§2.6) |
| `(TRANS, MODE, exits)` | `TRANS.source_mode` (§4.2) | `MODE.outgoing_transitions` (§2.7) |
| `(TRANS, MODE, enters)` | `TRANS.target_mode` (§4.2) | `MODE.incoming_transitions` (§2.7) |
| `(TRANS, GUARD, guarded_by)` | `TRANS.guard` (§4.2) | `GUARD.used_by_transitions` (§2.7) |
| `(GUARD, IFACE, observes)` | `GUARD.related_interfaces` (§4.3) | `Interface.related_guards` (§2.6) |

**Implementation note for Phase 2B:** `ConsistencyValidator._get_all_embedded_links()` must be extended with cases for `Mode`, `Transition`, and `Guard` that extract ALL fields listed above. The validator does NOT need special handling for single-valued fields (`source_mode`, `target_mode`, `guard`) — they are simply wrapped as `[field_value]` if non-empty before being returned in the links list.

---

## 3. Module Tree

```
aero_prop_logic_harness/
├── models/                          # [EXISTING — EXTEND]
│   ├── common.py                    # Extend ID_PATTERN, PREFIX_TO_TYPE, ArtifactType
│   ├── mode.py                      # [NEW — Phase 2 Core] MODE artifact model
│   ├── transition.py                # [NEW — Phase 2 Core] TRANS artifact model
│   ├── guard.py                     # [NEW — Phase 2 Core] GUARD predicate model
│   ├── trace.py                     # Extend TraceLinkType, VALID_TRACE_DIRECTIONS
│   ├── requirement.py               # [EXTEND — Phase 2A] Add linked_modes, linked_transitions, linked_guards (§2.6)
│   ├── function.py                  # [EXTEND — Phase 2A] Add related_modes, related_transitions (§2.6)
│   ├── interface.py                 # [EXTEND — Phase 2A] Add related_modes, related_guards (§2.6)
│   └── abnormal.py                  # [EXTEND — Phase 2A] Add related_modes, related_transitions (§2.6)
│
├── loaders/
│   └── artifact_loader.py           # [EXTEND] Register new PREFIX_TO_DIRECTORY + model classes
│
├── services/
│   ├── artifact_registry.py         # [EXTEND] Handle new types in _add_item()
│   └── mode_graph.py                # [NEW — Phase 2 Core] Build mode/transition graph from registry
│
├── validators/
│   ├── consistency_validator.py     # [EXTEND] Add embedded-link cases for MODE/TRANS/GUARD
│   ├── mode_validator.py            # [NEW — Phase 2 Core] Structural completeness checks
│   │                                #   - unreachable state detection
│   │                                #   - dead transition detection
│   │                                #   - missing initial state
│   │                                #   - guard completeness
│   └── coverage_validator.py        # [NEW — Phase 2 Core] Abnormal coverage checker
│                                    #   - every ABN has entry path into mode graph
│                                    #   - every degraded mode has recovery path or explicit dead-end
│
├── reporters/                       # [NEW — Phase 2.5+]
│   └── mode_report.py              # Export mode graph as text/DOT/JSON (Phase 2.5+)
│
├── path_constants.py                # [NO CHANGE] Already handles arbitrary subdirs
├── cli.py                           # [EXTEND] Add new commands for Phase 2
└── __init__.py                      # [EXTEND] Version bump
```

### Module responsibility and phase assignment

| Module | Responsibility | Phase |
|---|---|---|
| `models/mode.py` | MODE artifact: represents a named operating mode with entry/exit conditions, parent mode (for hierarchy), and bound actions | **Phase 2 Core** |
| `models/transition.py` | TRANS artifact: directed edge between two MODEs, with trigger signal, guard reference, priority, and bound action | **Phase 2 Core** |
| `models/guard.py` | GUARD artifact: reusable boolean predicate over IFACE signals, used by transitions | **Phase 2 Core** |
| `services/mode_graph.py` | Builds an in-memory directed graph of MODE nodes and TRANS edges from the ArtifactRegistry; provides reachability queries | **Phase 2 Core** |
| `validators/mode_validator.py` | Structural checks: initial state exists, all states reachable, no dead transitions, guard references resolve | **Phase 2 Core** |
| `validators/coverage_validator.py` | Domain checks: every ABN maps to at least one mode entry path; every degraded/fallback mode has recovery or explicit terminal annotation | **Phase 2 Core** |
| `reporters/mode_report.py` | Text and DOT export of mode graph for human review | **Phase 2.5+** |
| CLI `validate-modes` command | Run mode_validator + coverage_validator | **Phase 2 Core** |
| CLI `show-mode-graph` command | Print or export mode graph | **Phase 2.5+** |
| Scenario / test-vector executor | Execute transition sequences against stimuli | **Phase 3+** |
| Code generation | Generate state machine code from validated models | **Phase 3+** |
| Visual mode editor | GUI for editing mode graphs | **Phase 3+** |

---

## 4. New Artifact Design

### Design principles (grounded in existing codebase)

All new artifacts extend `ArtifactBase` from `common.py`, inheriting `id`, `artifact_type`, `version`, `status`, `provenance`, `review_status`, `tags`, `created_at`, `updated_at`, `notes`. This guarantees:
- Provenance tracking with `source_type`, `confidence`, `reviewed_by`
- Lifecycle states (draft → in_review → reviewed → frozen)
- Strict ID validation via `ID_PATTERN`
- `extra="forbid"` on Pydantic ConfigDict (no surprise fields)

### 4.1 MODE (prefix: `MODE-`)

**Necessity:** The Requirement model captures *what* the system must do. The Function model captures *logical functions*. Neither captures *which operating regime the engine is in* — the behavioral context that determines which functions are active, which interfaces are monitored, and which abnormals are relevant. The existing `ABN-0001` (N1 Sensor Loss) already references a `fallback_mode: "N2 Governing"` as a free-text string. Phase 2 must formalize this into a structured, traceable artifact.

**Relationship to existing artifacts:**
- REQ → MODE: Requirements constrain which modes must exist (trace type: `requires_mode`)
- FUNC → MODE: Functions are active within specific modes (embedded link: `active_in_modes`)
- ABN → MODE: Abnormals trigger entry into degraded modes (trace type: `triggers_mode`)
- IFACE → MODE: Interface signals serve as mode-observable indicators

**Minimum field set:**

```yaml
id: "MODE-0001"
artifact_type: "mode"
name: "Normal Governing"                    # Human-readable mode name
description: "Primary thrust control mode"  # What this mode represents
mode_type: "normal"                         # normal | degraded | emergency | startup | shutdown | test
parent_mode: ""                             # MODE-xxxx ID for hierarchical nesting (empty = top-level)
is_initial: false                           # Is this the initial/default mode?
entry_conditions:                           # Conditions required to enter this mode
  - "N1_Valid == true"
  - "N2_Valid == true"
exit_conditions: []                         # Conditions that force exit (if not via explicit transition)
active_functions: ["FUNC-0001"]             # FUNC-xxxx IDs active in this mode
monitored_interfaces: ["IFACE-0001"]        # IFACE-xxxx IDs monitored in this mode
related_requirements: ["REQ-0001"]          # REQ-xxxx IDs this mode addresses
related_abnormals: []                       # ABN-xxxx IDs relevant in this mode
incoming_transitions: []                    # TRANS-xxxx IDs that enter this mode (§2.7 reciprocal)
outgoing_transitions: []                    # TRANS-xxxx IDs that exit this mode (§2.7 reciprocal)
# ... inherits all ArtifactBase fields (provenance, review_status, etc.)
```

**What does NOT go here:** Transition logic (that's TRANS), guard predicates (that's GUARD), action implementation details, timing constraints (Phase 3+), simulation parameters. MODE does NOT reference GUARD directly — the path is MODE ← TRANS → GUARD (see §2.7).

**Trace integration:** New entries in `VALID_TRACE_DIRECTIONS`:
- `(REQ, MODE, requires_mode)` — requirement mandates this mode's existence
- `(ABN, MODE, triggers_mode)` — abnormal condition triggers entry to this mode
- `(MODE, FUNC, activates)` — mode activates a function
- `(MODE, IFACE, monitors)` — mode monitors an interface

### 4.2 TRANS (prefix: `TRANS-`)

**Necessity:** A state machine is defined by its transitions, not just its states. The existing trace model captures *static* relationships (REQ implements FUNC). Transitions capture *dynamic* relationships: under condition X, the system moves from mode A to mode B with action Y. Currently, `Requirement.triggers` and `Abnormal.entry_conditions` are free-text lists — they describe triggers but not the structured from→to→guard→action chain.

**Relationship to existing artifacts:**
- TRANS connects two MODEs (source_mode → target_mode)
- TRANS references GUARDs for conditional logic
- TRANS references FUNCs for actions to execute during transition
- TRANS is traceable to REQs that mandate the transition behavior

**Minimum field set:**

```yaml
id: "TRANS-0001"
artifact_type: "transition"
name: "Overspeed Entry"                     # Human-readable name
description: "Transition to overspeed protection mode"
source_mode: "MODE-0001"                    # MODE-xxxx: where we come from
target_mode: "MODE-0002"                    # MODE-xxxx: where we go to
trigger_signal: "IFACE-0001.N1_Speed"       # IFACE signal that initiates evaluation
guard: "GUARD-0001"                         # GUARD-xxxx: boolean gate (empty = always enabled)
priority: 100                               # Integer priority for arbitration (higher = evaluated first)
actions: ["FUNC-0001"]                      # FUNC-xxxx IDs to execute during transition
is_reversible: true                         # Can the system return from target to source?
related_requirements: ["REQ-0001"]          # REQ-xxxx IDs mandating this transition
related_abnormals: []                       # ABN-xxxx IDs relevant to this transition
# ... inherits all ArtifactBase fields
```

**What does NOT go here:** The guard logic itself (that's GUARD), timing deadlines (Phase 3+), execution implementation, test vectors.

**Trace integration:**
- `(TRANS, MODE, exits)` — transition exits source mode
- `(TRANS, MODE, enters)` — transition enters target mode
- `(TRANS, GUARD, guarded_by)` — transition is gated by this guard
- `(REQ, TRANS, requires_transition)` — requirement mandates this transition
- `(ABN, TRANS, triggers_transition)` — abnormal triggers this transition

### 4.3 GUARD (prefix: `GUARD-`)

**Necessity:** Guard predicates appear repeatedly across transitions. Factoring them out avoids duplication, enables reuse, and makes them independently reviewable and traceable. The existing `Interface.signals` and `Requirement.conditions` fields contain the raw material (signal names, threshold values) but lack structured boolean predicate representation. A GUARD is the structured bridge between IFACE signal definitions and TRANS conditional logic.

**Relationship to existing artifacts:**
- GUARD references IFACE signals as its input observables
- GUARD is used by TRANS as an enabling condition
- GUARD may relate to REQ conditions and ABN detection logic

**Minimum field set:**

```yaml
id: "GUARD-0001"
artifact_type: "guard"
name: "N1 Overspeed Threshold"              # Human-readable
description: "True when N1 exceeds 105% design speed"  # Human summary (NOT machine-checkable)
predicate:                                  # Structured predicate — machine-checkable authority (§4.7, §4.9)
  operator: "GT"                            #   GT | GE | LT | LE | EQ | NE | BOOL_TRUE | BOOL_FALSE
  signal_ref: "IFACE-0001.N1_Speed"         #   Pattern: IFACE-\d{4}\.\w+
  threshold: 105.0                          #   Numeric or boolean threshold
  unit: "%"                                 #   Unit for human reference (not machine-interpreted)
input_signals:                              # IFACE signal references (convenience, cross-checked by §4.9 grammar)
  - interface: "IFACE-0001"
    signal: "N1_Speed"
    unit: "%"
related_interfaces: ["IFACE-0001"]          # IFACE-xxxx IDs referenced
related_requirements: ["REQ-0001"]          # REQ-xxxx IDs that define this condition
related_abnormals: []                       # ABN-xxxx detection logic this guard formalizes
used_by_transitions: ["TRANS-0001"]         # TRANS-xxxx IDs that depend on this guard (§2.7 reciprocal)
# ... inherits all ArtifactBase fields
```

**What does NOT go here:** Transition logic (that's TRANS), executable code, timing windows, hysteresis parameters (Phase 3+ optional field).

**Field removed:** `threshold_type` (was: `upper_limit | lower_limit | range | boolean | compound`) — superseded by the structured `predicate.operator` field which encodes the same information with machine-parseable precision. See §4.9 for the full grammar specification.

**Trace integration:**
- `(GUARD, IFACE, observes)` — guard reads interface signals
- `(TRANS, GUARD, guarded_by)` — transition depends on this guard
- `(REQ, GUARD, defines_condition)` — requirement defines this guard's logic

### 4.4 Why NOT separate ACTION and SCENARIO artifacts at this stage

**ACTION:** The existing `Function` model already represents executable logical functions with `inputs`, `outputs`, `preconditions`, `postconditions`. A transition's `actions` field references FUNC-xxxx IDs directly. Creating a separate ACTION artifact would duplicate Function's role without adding value. If Phase 3+ needs finer-grained action decomposition (e.g., timed sequences), it can be introduced then as a FUNC subtype or new artifact.

**SCENARIO:** Test scenarios (stimulus → expected mode sequence → expected outputs) are Phase 3+ verification artifacts. Introducing them now would violate the "schema-first, execution-later" principle and the explicit Phase Scope Matrix in SYSTEM_SCOPE.md §6 which assigns test generation to Phase 3+. Phase 2 must deliver validated mode graphs first; scenarios validate those graphs and therefore depend on them.

### 4.5 Summary: ID prefix and directory mapping

| Prefix | Artifact type | Directory | Phase |
|---|---|---|---|
| `MODE-` | mode | `modes/` | Phase 2 Core |
| `TRANS-` | transition | `transitions/` | Phase 2 Core |
| `GUARD-` | guard | `guards/` | Phase 2 Core |

Required changes to `common.py`:
- `ID_PATTERN`: extend regex to `^(REQ|FUNC|IFACE|ABN|TERM|TRACE|MODE|TRANS|GUARD)-[0-9]{4}$`
- `ArtifactType`: add `MODE = "mode"`, `TRANSITION = "transition"`, `GUARD = "guard"`
- `PREFIX_TO_TYPE`: add `"MODE"`, `"TRANS"`, `"GUARD"` entries

### 4.6 Frozen Representation Decision: TRANS → IFACE

**Problem:** The TRANS field `trigger_signal: "IFACE-0001.N1_Speed"` implies a TRANS→IFACE relationship. The §5.1 data flow diagram shows `IFACE ← TRANS`. But the proposed `VALID_TRACE_DIRECTIONS` in §4.2 has no `(TRANS, IFACE, ...)` tuple. The relationship exists informally but is not formalized in the trace model.

**Options considered:**

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| A. Field-only | `trigger_signal` remains an embedded string on TRANS; no formal TRANS→IFACE trace | Simple; avoids trace explosion (R3) | No reverse-loop traceability for TRANS→IFACE |
| B. Trace-only | Remove `trigger_signal` field; require a `(TRANS, IFACE, triggered_by)` TraceLink | Full traceability | Loses convenience; TRANS becomes harder to read in isolation |
| C. Dual | Keep `trigger_signal` AND add `(TRANS, IFACE, triggered_by)` trace | Best of both | Redundancy; risk of drift between field and trace |

**Decision: Option A — Field-only.** Rationale:

1. The formal traceability path from transition logic to interface signals already exists via the GUARD chain: `TRANS --[guarded_by]--> GUARD --[observes]--> IFACE`. This covers the machine-checkable link.
2. `trigger_signal` is a human-readable convenience label identifying which signal *initiates evaluation* of the guard. It is NOT the formal condition (that's the GUARD).
3. Adding a TRANS→IFACE trace would create a parallel, redundant path that risks inconsistency with the GUARD→IFACE trace — violating the single-authority principle (see §4.7).
4. This choice limits trace explosion per Risk R3.

**Consequence:** `VALID_TRACE_DIRECTIONS` will NOT include any `(TRANS, IFACE, ...)` tuple. The TRANS `trigger_signal` field is validated only to confirm that the referenced IFACE ID exists (structural resolution check in `mode_validator.py`), NOT via the trace consistency system.

### 4.7 Frozen Authority: Condition-Expression Hierarchy

**Problem:** Three overlapping surfaces express "conditions" for mode transitions:

| Surface | Location | Format | Example |
|---|---|---|---|
| `MODE.entry_conditions` | mode.py | `list[str]` (free text) | `["N1_Valid == true", "N2_Valid == true"]` |
| `TRANS.trigger_signal` | transition.py | `str` (signal reference) | `"IFACE-0001.N1_Speed"` |
| `GUARD.predicate` | guard.py | Structured object (`AtomicPredicate \| CompoundPredicate`, see §4.9) | `{operator: GT, signal_ref: IFACE-0001.N1_Speed, threshold: 105.0}` |

Without a defined hierarchy, automated tools cannot know which surface to trust for machine-checkable condition analysis.

**Decision: GUARD is the single machine-checkable authority.**

| Surface | Authority level | Purpose | Machine-checkable? |
|---|---|---|---|
| `GUARD.predicate` | **Primary** | Canonical structured predicate for all automated analysis (§4.9 grammar) | **Yes** — Phase 2B validators and Phase 3+ tools MUST use this |
| `GUARD.description` | **Human summary** | Free-text human-readable description of what the guard evaluates; NOT machine-checkable, NOT authoritative | **No** — informational only |
| `TRANS.trigger_signal` | **Convenience label** | Identifies the initiating signal for human readability | **No** — only checked for IFACE ID existence |
| `MODE.entry_conditions` | **Human summary** | Documents mode entry intent for review; not parsed by tools | **No** — never machine-interpreted |

**Unified field-name decision (R3 freeze):** The machine-checkable authority field is named `predicate` (a structured Pydantic object per §4.9). The former working name `predicate_expression` (a free-text string) is **superseded and MUST NOT appear** in any artifact schema, grammar, gate, or implementation reference. All occurrences have been replaced as of R3. `GUARD.description` (inherited free text from `ArtifactBase.description` or the `description` field in §4.3) provides the human-readable summary and is explicitly NOT the machine-checkable authority.

**Enforcement rule:** Any Phase 2B+ validator or Phase 3+ tool that needs to evaluate a transition condition MUST read the GUARD artifact referenced by `TRANS.guard`, NOT the `MODE.entry_conditions` or `TRANS.trigger_signal` fields. If `TRANS.guard` is empty, the transition is unconditional (always fires when evaluated). The tool MUST use `GUARD.predicate` (the structured object), never `GUARD.description`.

**Consistency guidance (non-mandatory):** Authors SHOULD keep `MODE.entry_conditions`, `TRANS.trigger_signal`, and `GUARD.description` consistent with the referenced GUARD's `predicate`. A future Phase 3+ linter MAY flag inconsistencies. But only the GUARD `predicate` field is authoritative.

### 4.9 Frozen Minimal Grammar: GUARD.predicate

**Problem:** §4.7 declares GUARD the single machine-checkable authority. If the authority field were a free-text string (e.g., `"N1_Speed > 105.0"`), "machine-checkable" would be aspirational — no tool can parse an ungrammatical string. The authority designation is meaningless without a frozen grammar boundary.

**Decision: Structured object grammar (Pydantic-native).** The authority field is `predicate` — a nested Pydantic object that is validated at load time. No custom string parser required. No evaluator required. (The former working name `predicate_expression` is superseded — see §4.7 R3 freeze note.)

#### Atomic predicate

```yaml
predicate:
  operator: "GT"                    # REQUIRED — see allowed values below
  signal_ref: "IFACE-0001.N1_Speed" # REQUIRED — must match ^IFACE-\d{4}\.\w+$
  threshold: 105.0                  # REQUIRED for comparison ops; null for BOOL_TRUE/BOOL_FALSE
  unit: "%"                         # OPTIONAL — human reference only, not machine-interpreted
```

#### Compound predicate

```yaml
predicate:
  combinator: "AND"                 # REQUIRED — AND | OR | NOT
  operands:                         # REQUIRED — list of atomic or compound predicates
    - operator: "GT"
      signal_ref: "IFACE-0001.N1_Speed"
      threshold: 105.0
      unit: "%"
    - operator: "EQ"
      signal_ref: "IFACE-0002.N1_Valid"
      threshold: true
```

#### Allowed tokens

| Token | Allowed values | Meaning |
|---|---|---|
| `operator` | `GT`, `GE`, `LT`, `LE`, `EQ`, `NE`, `BOOL_TRUE`, `BOOL_FALSE` | Comparison or boolean check |
| `combinator` | `AND`, `OR`, `NOT` | Logical combination (NOT takes exactly 1 operand; AND/OR take 2+) |
| `signal_ref` | Must match `^IFACE-\d{4}\.\w+$` | Reference to a signal on an existing Interface artifact |
| `threshold` | `float`, `int`, `bool`, or `null` | Comparison value; required for GT/GE/LT/LE/EQ/NE; must be null for BOOL_TRUE/BOOL_FALSE |
| `unit` | Any string or empty | Human-readable unit label; never machine-interpreted |

#### What is explicitly prohibited

- Free-form natural language (e.g., `"when N1 speed is high"`)
- Arithmetic expressions (e.g., `"N1_Speed * 1.05 > threshold"`) — Phase 3+ if needed
- Nested function calls (e.g., `"avg(N1_Speed, window=5s) > 105"`) — Phase 3+ if needed
- Time-based predicates (e.g., `"N1_Speed > 105 FOR 3s"`) — Phase 3+ if needed
- References to non-IFACE artifacts in `signal_ref` — guards observe interface signals only

#### Machine-checkable boundary

Phase 2B validators CAN structurally verify:

| Check | How |
|---|---|
| `signal_ref` resolves to an existing IFACE + signal | Parse the `IFACE-xxxx` prefix, look up in registry, verify signal name exists in Interface.signals |
| `operator` is in allowed set | Pydantic enum validation at load time |
| `combinator` operand count | `NOT` has exactly 1 operand; `AND`/`OR` have 2+ |
| `threshold` type matches operator | Comparison operators require numeric; BOOL_TRUE/BOOL_FALSE require null |
| All `signal_ref` values are covered by `related_interfaces` | Cross-check: every IFACE-xxxx prefix in predicate must appear in GUARD.related_interfaces |

Phase 2B validators CANNOT (requires Phase 3+ or human review):

| Check | Why |
|---|---|
| Whether the predicate is physically meaningful | Domain engineering judgment (e.g., is 105% the right threshold?) |
| Whether two predicates semantically overlap | Requires symbolic evaluation — see P2-C4-R |
| Whether threshold values are consistent with requirements | Requires cross-referencing REQ free-text conditions |

#### Pydantic implementation guidance

```python
class PredicateOperator(str, Enum):
    GT = "GT"; GE = "GE"; LT = "LT"; LE = "LE"
    EQ = "EQ"; NE = "NE"
    BOOL_TRUE = "BOOL_TRUE"; BOOL_FALSE = "BOOL_FALSE"

class PredicateCombinator(str, Enum):
    AND = "AND"; OR = "OR"; NOT = "NOT"

class AtomicPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: PredicateOperator
    signal_ref: str  # validated by field_validator against ^IFACE-\d{4}\.\w+$
    threshold: float | int | bool | None = None
    unit: str = ""

class CompoundPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    combinator: PredicateCombinator
    operands: list["AtomicPredicate | CompoundPredicate"]  # recursive

# GUARD.predicate field type:
predicate: AtomicPredicate | CompoundPredicate
```

This is implementation guidance, not binding code. The Phase 2A implementer may adjust field names or validation logic, but the grammar boundary (allowed operators, combinators, signal_ref pattern, threshold typing) is FROZEN.

---

### 4.8 Frozen Representation Decision: TRANS.actions ↔ Function.related_transitions

**Problem:** §2.6 freezes `Function.related_transitions: list[str] = []` as an additive field on Function. §4.2 defines `TRANS.actions: list[str]` as a list of FUNC-xxxx IDs. But the formal relationship between these two fields is not frozen: is it field-only, trace-backed, dual, or excluded from consistency scope?

**Options considered:**

| Option | Mechanism | Pros | Cons |
|---|---|---|---|
| A. Field-only, excluded from consistency scope | Both fields exist; NOT fed into `_get_all_embedded_links()`; no `(TRANS, FUNC, ...)` trace | Simple; avoids trace explosion; `mode_validator.py` does structural resolution | No automated reverse-loop check; drift possible between TRANS.actions and Function.related_transitions |
| B. Trace-backed | Remove `TRANS.actions`; require `(TRANS, FUNC, executes)` TraceLink | Full traceability | Loses convenience; TRANS unreadable without joining to traces |
| C. Dual (field + trace) | Keep both fields + add `(TRANS, FUNC, executes)` trace direction | Full traceability + convenience | Redundancy; 3 surfaces for one relationship; trace explosion per R3 |
| D. Field-only, IN consistency scope | Both fields fed into `_get_all_embedded_links()`; require TraceLink counterpart | Automated consistency | Requires `(TRANS, FUNC, executes)` trace direction, pushing toward option C |

**Decision: Option A — Field-only, explicitly excluded from consistency scope.** Rationale:

1. **Nature of the relationship:** `TRANS.actions` represents "functions to invoke during this transition" — an ephemeral, execution-time binding. This is fundamentally different from persistent engineering relationships like `REQ → FUNC` (implements) or `FUNC → IFACE` (uses). The existing P0/P1 trace skeleton captures *structural* engineering relationships; transition actions are *behavioral* bindings that belong to the mode graph, not the trace skeleton.

2. **Structural resolution, not trace consistency:** `mode_validator.py` (Phase 2B) MUST verify that every FUNC ID in `TRANS.actions` resolves to an existing Function artifact. This is a **structural resolution check** (like checking that TRANS.source_mode points to a real MODE), not a **trace consistency check**. The check lives in `mode_validator.py`, not in `ConsistencyValidator`.

3. **Reciprocal field purpose:** `Function.related_transitions` exists for human readability and query convenience (e.g., "which transitions use this function?"). It is NOT consumed by `_get_all_embedded_links()`. A Phase 3+ linter MAY flag drift between `TRANS.actions` and `Function.related_transitions`, but this is advisory, not gate-blocking.

4. **Trace explosion control:** Adding `(TRANS, FUNC, executes)` would add N trace links per mode graph (one per transition-action pair). For a system with 50 transitions averaging 2 actions each, that's 100 additional traces — significant bloat for a relationship already captured in the artifact fields.

**Consequences:**
- `VALID_TRACE_DIRECTIONS` will NOT include any `(TRANS, FUNC, ...)` tuple.
- `ConsistencyValidator._get_all_embedded_links()` will NOT extract `TRANS.actions` or `Function.related_transitions`. These fields are invisible to the trace consistency system.
- `mode_validator.py` MUST include a structural resolution check: every ID in `TRANS.actions` must resolve to an existing FUNC artifact in the registry.
- Change-impact analysis for "what happens if I modify FUNC-0001?" flows via `mode_graph.py` query (`which transitions use this function?`), NOT via the trace graph.

---

## 5. P0/P1 → Phase 2 Data Flow

### 5.1 Input mapping

```
┌────────────────────────────────────────────────────────────────────────┐
│                     P0/P1 Knowledge Base                              │
│                                                                       │
│  REQ-xxxx ─────┬──[requires_mode]──────────► MODE-xxxx               │
│                ├──[requires_transition]──────► TRANS-xxxx             │
│                └──[defines_condition]────────► GUARD-xxxx             │
│                                                                       │
│  FUNC-xxxx ────┬──[active_in_modes] ◄────── MODE-xxxx                │
│                └──[actions] ◄──────────────── TRANS-xxxx (§4.8: field-only, no trace) │
│                                                                       │
│  IFACE-xxxx ───┬──[trigger_signal] ◄──────── TRANS-xxxx              │
│                ├──[input_signals] ◄────────── GUARD-xxxx             │
│                └──[monitored_interfaces] ◄── MODE-xxxx               │
│                                                                       │
│  ABN-xxxx ─────┬──[triggers_mode]──────────► MODE-xxxx (degraded)    │
│                └──[triggers_transition]─────► TRANS-xxxx              │
│                                                                       │
│  TRACE-xxxx ───── Extended with new valid directions ──────────►     │
│                                                                       │
└────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Phase 2 Mode Graph                                │
│                                                                       │
│  ModeGraph (in-memory, built from ArtifactRegistry)                  │
│    ├── nodes: Dict[str, MODE]                                        │
│    ├── edges: Dict[str, TRANS]                                       │
│    ├── guards: Dict[str, GUARD]                                      │
│    ├── initial_mode: str                                             │
│    └── methods:                                                      │
│         ├── reachable_from(mode_id) → Set[str]                       │
│         ├── dead_transitions() → List[str]                           │
│         ├── unreachable_modes() → List[str]                          │
│         └── abnormal_coverage() → Dict[str, List[str]]               │
│                                                                       │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Input classification

| Input | Required / Optional | Rationale |
|---|---|---|
| At least 1 MODE with `is_initial: true` | **Required** | Graph must have a defined starting point |
| At least 1 TRANS connecting two MODEs | **Required** | A mode graph with no transitions is vacuous |
| GUARD for each TRANS that has conditional logic | **Required** where guard field is non-empty | Unresolved guard references are structural errors |
| REQ traceback for each MODE and TRANS | **Optional but strongly recommended** | Validates engineering justification exists |
| FUNC references in MODE.active_functions and TRANS.actions | **Optional** | Can be populated incrementally |
| ABN → MODE mapping for degraded modes | **Required** for modes where `mode_type != "normal"` | Every degraded/emergency mode must justify its existence |
| IFACE signal references in GUARD.input_signals | **Required** | Guards must ground in observable signals |

### 5.3 Demo-scale vs formal baseline separation

**Critical rule:** Phase 2 inherits the exact same boundary enforcement from P0/P1.

- Phase 2 demo artifacts go in `artifacts/examples/minimal_demo_set/modes/`, `artifacts/examples/minimal_demo_set/transitions/`, `artifacts/examples/minimal_demo_set/guards/`
- Phase 2 formal artifacts go in `artifacts/modes/`, `artifacts/transitions/`, `artifacts/guards/`
- The existing `.aplh/freeze_gate_status.yaml` per-directory binding still applies
- `iter_artifact_yamls()` in `path_constants.py` already handles arbitrary subdirectories — **no changes needed** to the shared traversal
- `is_formal_baseline_root()` continues to enforce `freeze-complete` only for `artifacts/` root

**How Phase 2 avoids treating demo as formal:** The same mechanism as P0/P1 — `freeze-readiness` checks `baseline_scope` against directory identity. A Phase 2 `validate-modes` command must accept a `--dir` parameter and respect the same boundary. Phase 2 gates that pass on demo-scale must output "Demo-scale mode graph checks passed" — never "Ready for Formal Mode Freeze."

### 5.4 Key dependencies

| Dependency | Type | Risk if missing |
|---|---|---|
| `ArtifactBase` extensibility | Hard | Cannot create MODE/TRANS/GUARD models without extending `common.py` enums |
| `PREFIX_TO_TYPE` / `ID_PATTERN` extension | Hard | New artifacts won't load |
| `ArtifactRegistry` new-type handling | Hard | `mode_graph.py` cannot build graph |
| `VALID_TRACE_DIRECTIONS` extension | Hard | Traces between new and existing types will be rejected |
| Existing demo set content | Soft | Phase 2 demo must build *alongside* existing demo, not replace it |
| `path_constants.py` traversal | None | Already handles arbitrary subdirectories correctly |

---

## 6. Gate Design

### 6.0 Gate Governance Tiers

All gate items in Phase 2 are classified into one of three governance tiers. This classification is FROZEN and must be respected by all Phase 2 implementation sessions.

| Tier | Name | Enforcement | Phase progression effect | Record format |
|---|---|---|---|---|
| **T1** | Programmatic gate | Automated check in CLI or pytest | **Blocks** — phase cannot advance until check passes (exit 0) | Test result in CI / pytest output |
| **T2** | Manual signoff gate | Human reviewer explicitly signs off | **Blocks** — phase cannot advance until signoff is recorded in `.aplh/` | `reviewer`, `date`, `verdict` fields in `.aplh/review_signoffs.yaml` |
| **T3** | Advisory review item | Flagged for human attention; reviewer may note findings | **Does not block** — phase can advance even if reviewer flags concerns | Reviewer notes in `.aplh/review_signoffs.yaml` (optional) |

**Why three tiers?** A binary "gate-blocking / not-gate-blocking" system is too coarse. Some checks (P2-C4-R, P2-D4-R) require engineering judgment that cannot be automated, but their safety implications are significant enough that "just a note" is insufficient. The manual signoff tier fills this gap: the check is not automated, but a human must explicitly declare "I reviewed this and it is acceptable" before the phase advances.

**Tier assignment rules:**
- If a check can be expressed as a deterministic program (pytest, CLI exit code): **T1**
- If a check requires domain judgment AND has safety/correctness implications: **T2**
- If a check is informational with no direct safety impact: **T3**

**Phase-dependent escalation:** A review item's tier may differ by phase. For example, an item may be T3 at Phase 2B (synthetic test data where the test author controls all inputs) but escalated to T2 at Phase 2C (real demo data authored by engineers).

### Gate P2-A: Phase 2 Artifact Schema Ready

**Objective:** Confirm that MODE, TRANS, and GUARD Pydantic models exist, validate correctly, and integrate with the existing loader/registry pipeline.

**Input conditions:**
- `models/mode.py`, `models/transition.py`, `models/guard.py` exist
- `common.py` enums and `ID_PATTERN` extended
- `artifact_loader.py` registers new types
- JSON schemas exported via `dump_schemas.py`
- Templates created in `templates/`

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-A1 | MODE model loads from YAML | `load_artifact()` succeeds for a valid `mode-0001.yaml` | **T1** |
| P2-A2 | TRANS model loads from YAML | `load_artifact()` succeeds for a valid `trans-0001.yaml` | **T1** |
| P2-A3 | GUARD model loads from YAML | `load_artifact()` succeeds for a valid `guard-0001.yaml` | **T1** |
| P2-A4 | Invalid artifacts rejected | Pydantic `extra="forbid"` rejects unknown fields | **T1** |
| P2-A5 | ID validation works | `MODE-XXXX`, `TRANS-XXXX`, `GUARD-XXXX` patterns enforced | **T1** |
| P2-A6 | Existing P0/P1 tests still pass | `python -m pytest` exits 0 with zero regressions | **T1** |

**Programmatic verification:** `python -m pytest` + `python -m aero_prop_logic_harness validate-artifacts --dir <test_dir_with_new_types>`

**Common failure modes:**
- Forgetting to extend `PREFIX_TO_DIRECTORY` in `artifact_loader.py`
- Breaking `ID_PATTERN` regex when extending it
- New model fields conflicting with `ArtifactBase` reserved names

**Boundary with P0/P1:** This gate does NOT modify P0/P1 gate logic. `freeze-readiness` relational coverage checks remain unchanged (they check P0/P1 relation types only).

---

### Gate P2-B: Transition Completeness

**Objective:** Confirm that the mode graph has no structural holes — every mode is reachable, every transition has valid endpoints, and at least one initial mode is defined.

**Input conditions:**
- Gate P2-A passed
- At least one mode graph exists (demo-scale or formal)

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-B1 | Initial mode exists | Exactly one MODE has `is_initial: true` per mode graph | **T1** |
| P2-B2 | All modes reachable | BFS/DFS from initial mode reaches every MODE | **T1** |
| P2-B3 | No dangling transitions | Every TRANS `source_mode` and `target_mode` resolves to an existing MODE | **T1** |
| P2-B4 | No self-loops without justification | TRANS where `source_mode == target_mode` must have a non-empty `rationale` or `notes` | **T1** |
| P2-B5 | Guard references resolve | Every non-empty TRANS `guard` field points to an existing GUARD | **T1** |

**Programmatic verification:** `python -m aero_prop_logic_harness validate-modes --dir <target>` (new CLI command)

**Common failure modes:**
- Multiple initial modes declared (ambiguous start)
- Orphan mode created but never targeted by any transition
- Guard referenced before GUARD artifact authored

**Boundary with P0/P1:** Independent gate. Does not interact with `freeze-readiness`.

---

### Gate P2-C: Unreachable States / Dead Transitions

**Objective:** Detect graph pathology — modes that can never be entered, transitions that can never fire.

**Input conditions:**
- Gate P2-B passed

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-C1 | No unreachable modes | Every non-initial MODE is a `target_mode` of at least one TRANS | **T1** |
| P2-C2 | No dead-end modes without annotation | Modes with no outgoing TRANS must have `mode_type` in `{shutdown, emergency}` or explicit `notes` explaining why | **T1** |
| P2-C3 | No orphan transitions | Every TRANS is connected to at least one reachable source mode | **T1** |

**Programmatic verification:** Part of `validate-modes` command output.

**Non-programmable review items (require engineering judgment):**

| # | Review item | Why non-programmable | Governance tier |
|---|---|---|---|
| P2-C4-R | Priority conflicts with overlapping guards | Determining whether two GUARD predicates "overlap" requires semantic evaluation of structured predicates (§4.9). While the grammar is now machine-parseable, detecting overlap between `N1_Speed > 105` and `N1_Speed > 100` requires range analysis beyond structural validation. | **T3 (advisory)** at Phase 2B; **T2 (manual signoff)** at Phase 2C and P2-F |

**Manual signoff requirement at Phase 2C:** Before Gate P2-F can pass, a human reviewer MUST record in `.aplh/review_signoffs.yaml` that they have inspected all transitions sharing the same `source_mode` for priority conflicts with potentially overlapping guards. The signoff record must include: reviewer name, date, list of source_modes inspected, and verdict.

**Common failure modes:**
- Degraded mode created but no transition path leads to it
- Priority collision causing nondeterministic behavior (caught by P2-C4-R manual signoff at Phase 2C)
- Copy-paste error giving two transitions identical source/target/guard

---

### Gate P2-D: Abnormal Fallback / Recovery Coverage

**Objective:** Every abnormal condition in the knowledge base must have a corresponding entry path into the mode graph, and every degraded/emergency mode must either have a recovery path or be explicitly marked terminal.

**Input conditions:**
- Gate P2-C passed
- ABN artifacts exist in the target directory

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-D1 | Every ABN has a mode mapping | Each ABN-xxxx is referenced by at least one MODE's `related_abnormals` or one TRANS's `related_abnormals` | **T1** |
| P2-D2 | Every degraded mode has recovery or terminal flag | Modes with `mode_type: "degraded"` have at least one outgoing TRANS back to a normal mode, OR have explicit annotation in `notes` as terminal | **T1** |
| P2-D3 | Emergency modes are reachable | Modes with `mode_type: "emergency"` are target of at least one TRANS | **T1** |

**Programmatic verification:** Part of `validate-modes --coverage` flag.

**Non-programmable review items (require engineering judgment):**

| # | Review item | Why non-programmable | Governance tier |
|---|---|---|---|
| P2-D4-R | ABN severity matches mode type | `severity_hint` is a free-text string on ABN (not an enum), and `mode_type` is a constrained enum on MODE. Mapping between them requires domain judgment (e.g., "hazardous" → emergency vs. degraded depends on system context). A future Phase 3+ enhancement MAY formalize `severity_hint` into an enum and promote this to T1. | **T3 (advisory)** at Phase 2B; **T2 (manual signoff)** at Phase 2C and P2-F |

**Manual signoff requirement at Phase 2C:** Before Gate P2-F can pass, a human reviewer MUST record in `.aplh/review_signoffs.yaml` that they have verified the severity↔mode_type alignment for every ABN→MODE mapping in the demo data. The signoff record must include: reviewer name, date, list of ABN-MODE pairs inspected, and verdict.

**Common failure modes:**
- ABN artifact exists from P0/P1 but no Phase 2 mode graph edge references it
- Degraded mode created but recovery path forgotten
- Severity mismatch (major abnormal mapped to emergency mode, or catastrophic mapped to degraded — caught by P2-D4-R manual signoff at Phase 2C)

---

### Gate P2-E: Trace Extension Ready

**Objective:** Confirm that traceability between P0/P1 artifacts and Phase 2 artifacts is structurally valid.

**Input conditions:**
- Gate P2-A passed
- New trace direction tuples added to `VALID_TRACE_DIRECTIONS`

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-E1 | New trace types registered | `VALID_TRACE_DIRECTIONS` includes all Phase 2 pairs | **T1** |
| P2-E2 | `TraceLinkType` enum extended | New values: `requires_mode`, `triggers_mode`, `activates`, `monitors`, `guarded_by`, etc. | **T1** |
| P2-E3 | Cross-type traces validate | A TRACE from REQ-xxxx to MODE-xxxx loads without error | **T1** |
| P2-E4 | Existing P0/P1 traces unaffected | All 11 demo traces still load and validate | **T1** |

**NOTE:** Bidirectional consistency checking (extending `ConsistencyValidator._get_all_embedded_links()` for new types) is a **Phase 2B deliverable**, not Phase 2A. See §7 Phase 2B deliverable #4. The validator extension depends on BOTH the additive fields defined in §2.6 AND the reciprocal fields defined in §2.7 being present in the model code, AND the graph infrastructure from `mode_graph.py` being available. Gate P2-E at Phase 2A scope covers items E1–E4 only.

**Phase 2B addition — P2-E5:**

| # | Check | Pass criterion | Tier | Phase |
|---|---|---|---|---|
| P2-E5 | Bidirectional consistency (§2.6 + §2.7) | `ConsistencyValidator` checks embedded links for MODE/TRANS/GUARD using: (a) all 9 additive fields from §2.6, AND (b) all 3 reciprocal fields from §2.7 — specifically `MODE.incoming_transitions`, `MODE.outgoing_transitions`, `GUARD.used_by_transitions`. The complete reverse-loop coverage matrix is defined in §2.7. | **T1** | **Phase 2B** |

**Common failure modes:**
- Adding new `TraceLinkType` values but forgetting to add them to `VALID_TRACE_DIRECTIONS`
- Breaking existing trace validation by modifying the set incorrectly
- (Phase 2B) Extending `_get_all_embedded_links()` but missing one of the 9 additive fields from §2.6
- (Phase 2B) Extending `_get_all_embedded_links()` but missing one of the 3 reciprocal fields from §2.7 (`MODE.incoming_transitions`, `MODE.outgoing_transitions`, `GUARD.used_by_transitions`)

---

### Gate P2-F: Demo-Scale Execution Readiness

**Objective:** The minimal demo set has been extended with Phase 2 artifacts and passes all Phase 2 gates at demo-scale.

**Input conditions:**
- Gates P2-A through P2-E passed
- Demo-scale Phase 2 artifacts exist in `artifacts/examples/minimal_demo_set/`

**Check items:**

| # | Check | Pass criterion | Tier |
|---|---|---|---|
| P2-F1 | Demo mode graph loads | `validate-modes --dir artifacts/examples/minimal_demo_set` exits 0 | **T1** |
| P2-F2 | Demo covers overspeed scenario | At least: Normal → Overspeed Protection transition exists, triggered by N1 > 105% | **T1** |
| P2-F3 | Demo covers N1 sensor loss | ABN-0001 maps to a degraded mode with fallback to N2 Governing | **T1** |
| P2-F4 | All P0/P1 gates still pass | `python -m pytest` exits 0; `validate-artifacts`, `check-trace` on demo still pass | **T1** |
| P2-F5 | Output is demo-scale only | `freeze-readiness --dir artifacts/examples/minimal_demo_set` still says "Demo-scale gate checks passed" | **T1** |

**Critical boundary:** This gate DOES NOT produce "Ready for Formal Baseline Freeze" — ever. It only confirms demo-scale structural readiness.

---

## 7. Development Sequence and Milestones

### Phase 2A: Schema + Artifact + Trace Extension

**Deliverables:**
1. `models/mode.py` — MODE Pydantic model with reciprocal fields `incoming_transitions`, `outgoing_transitions` (§2.7)
2. `models/transition.py` — TRANS Pydantic model
3. `models/guard.py` — GUARD Pydantic model with reciprocal field `used_by_transitions` (§2.7) and structured `predicate` field (§4.9)
4. `models/predicate.py` — `AtomicPredicate`, `CompoundPredicate`, `PredicateOperator`, `PredicateCombinator` Pydantic models (§4.9 grammar)
5. Extended `common.py`: `ArtifactType`, `PREFIX_TO_TYPE`, `ID_PATTERN`
6. Extended `trace.py`: `TraceLinkType`, `VALID_TRACE_DIRECTIONS` (NO `(TRANS, IFACE, ...)` — §4.6; NO `(TRANS, FUNC, ...)` — §4.8)
7. Extended `artifact_loader.py`: `PREFIX_TO_DIRECTORY`, `_get_model_class()`
8. Additive fields on P0/P1 models per §2.6: `requirement.py`, `function.py`, `interface.py`, `abnormal.py` (9 new `list[str]` fields total, all defaulting to `[]`)
9. JSON schemas exported for new types (including predicate sub-schema)
10. YAML templates for new types in `templates/`
11. Unit tests for new models (load, validate, reject invalid) + regression tests confirming existing artifacts still load + predicate grammar validation tests (valid atomic, valid compound, invalid free-text rejected)

**Does NOT include:** Mode graph construction, structural validators, demo data, CLI commands, `ConsistencyValidator` extension (that's Phase 2B), predicate evaluator (that's Phase 3+).

**Pass criterion:** Gate P2-A + Gate P2-E items E1–E4 pass. `python -m pytest` exits 0 with no P0/P1 regressions. (P2-E5 bidirectional consistency is a Phase 2B gate item — see §6 Gate P2-E note.)

**Entry to next:** Allowed only after P2-A and P2-E (E1–E4) are green.

---

### Phase 2B: Transition Logic + Validators

**Deliverables:**
1. `services/mode_graph.py` — in-memory graph builder
2. `validators/mode_validator.py` — structural checks (P2-B, P2-C programmable items)
3. `validators/coverage_validator.py` — abnormal coverage checks (P2-D programmable items)
4. Extended `consistency_validator.py` — embedded link extraction for new types, covering BOTH: (a) all 9 additive fields from §2.6 (P0/P1 models' new `linked_*`/`related_*` fields), AND (b) all 3 reciprocal fields from §2.7 (new model fields: `MODE.incoming_transitions`, `MODE.outgoing_transitions`, `GUARD.used_by_transitions`), AND (c) all TRANS embedded link fields from §2.7 (`source_mode`, `target_mode`, `guard`, `related_requirements`, `related_abnormals`). This satisfies Gate P2-E5 (bidirectional consistency). The complete set of fields to extract is enumerated in the §2.7 reverse-loop coverage matrix.
5. New CLI command: `validate-modes --dir <path>` with optional `--coverage` flag
6. Tests: unit tests for graph construction, validator logic; integration tests using `tmp_path` + real CLI; reverse-loop tests covering ALL directions in the §2.7 coverage matrix (not just §2.6 directions)
7. Human review checklist document for non-programmable items P2-C4-R and P2-D4-R (see §6 Gate P2-C and P2-D)

**Does NOT include:** Demo data authoring, report export, execution engine, simulation.

**Pass criterion:** Gates P2-B (T1), P2-C (T1 items: C1–C3), P2-D (T1 items: D1–D3), and P2-E5 (T1) pass against synthetic test data in `tmp_path`. `python -m pytest` exits 0. Review items P2-C4-R and P2-D4-R are **T3 (advisory)** at this phase — flagged in test output for awareness, but do not block Phase 2B→2C progression. They escalate to **T2 (manual signoff)** at Phase 2C.

**Entry to next:** Allowed only after P2-B through P2-D are green on synthetic data.

---

### Phase 2C: Demo-Scale Execution Readiness

**Deliverables:**
1. Demo Phase 2 artifacts in `artifacts/examples/minimal_demo_set/`:
   - `modes/mode-0001.yaml` (Normal Governing)
   - `modes/mode-0002.yaml` (Overspeed Protection)
   - `modes/mode-0003.yaml` (N2 Fallback Governing — degraded)
   - `transitions/trans-0001.yaml` (Normal → Overspeed, guard: N1 > 105%)
   - `transitions/trans-0002.yaml` (Normal → N2 Fallback, trigger: ABN-0001)
   - `transitions/trans-0003.yaml` (N2 Fallback → Normal, recovery)
   - `guards/guard-0001.yaml` (N1 Overspeed Threshold)
   - `guards/guard-0002.yaml` (N1 Sensor Valid)
   - Trace links connecting MODE/TRANS/GUARD to existing REQ/FUNC/IFACE/ABN
2. Updated demo `.aplh/freeze_gate_status.yaml` (still `demo-scale`)
3. Integration tests confirming Gate P2-F items

**Does NOT include:** Formal baseline population, scenario execution, report generation.

**Pass criterion:** Gate P2-F passes (T1 items). All P0/P1 gates still pass. `python -m pytest` exits 0. **Additionally:** T2 manual signoffs for P2-C4-R and P2-D4-R must be recorded in `.aplh/review_signoffs.yaml` with reviewer name, date, and verdict.

**Entry to next:** Allowed only after P2-F (T1) is green AND T2 manual signoffs are complete AND general human review of demo data quality.

---

### Phase 2D: Phase 3 Interface Preparation

**Deliverables:**
1. `reporters/mode_report.py` — text and DOT format export
2. Documentation: `docs/PHASE2_HANDOFF.md` describing mode graph schema, extension points, and Phase 3 entry conditions
3. Updated `docs/REVIEW_GATES.md` with Phase 2 gates
4. Updated `docs/ARTIFACT_MODEL.md` §7 extension points reflecting actual Phase 2 implementation
5. Risk assessment for Phase 3 (scenario execution, timing, simulation)

**Does NOT include:** Scenario executor, code generation, simulation engine, UI.

**Pass criterion:** Documentation reviewed. `mode_report.py` produces valid output for demo data. `python -m pytest` exits 0.

---

## 8. Risk Register

### Risk R1: Demo/Formal Boundary Re-pollution

**Description:** Phase 2 development accidentally creates artifacts or gate logic that blurs the demo-scale / formal-baseline boundary.

**Why real now:** Phase 2 adds new artifact types to `artifacts/examples/minimal_demo_set/`. If a developer forgets to maintain the boundary or the new `validate-modes` command doesn't respect `iter_artifact_yamls()` traversal rules, demo content could leak into formal scope assessments.

**Consequence:** Formal freeze-readiness could pass on demo data, destroying the P0/P1 gate integrity that was just repaired in v4.1.

**Mitigation:**
- New CLI commands MUST use `iter_artifact_yamls()` from `path_constants.py` for all directory traversal (never raw `glob`)
- Add integration test: `test_demo_mode_graph_does_not_affect_formal_freeze_readiness`
- `validate-modes` output must include explicit "Demo-scale" / "Formal" label
- Review gate P2-F explicitly checks that P0/P1 gates are unaffected

---

### Risk R2: State/Mode Design Over-abstraction

**Description:** The MODE/TRANS/GUARD schema is designed too abstractly, becoming a generic graph notation rather than a propulsion-control-specific mode representation.

**Why real now:** The planning phase is inherently abstract. Without concrete engine scenarios constraining the design, there is temptation to add flexibility that serves no real engineering need (e.g., nested hierarchical mode trees, parallel regions, history pseudostates).

**Consequence:** Artifacts become hard to author, hard to review, and disconnected from actual engine behavior. Engineers won't use them.

**Mitigation:**
- Phase 2C demo must model the actual overspeed protection and N1 sensor loss scenarios from the existing demo set — not abstract examples
- `mode_type` enum is constrained to 6 concrete values, not extensible without schema change
- Hierarchical nesting is optional (`parent_mode: ""` is the default) — forced to justify if used
- No parallel regions or history states in Phase 2; deferred to Phase 3+ if needed

---

### Risk R3: Trace Extension Explosion

**Description:** Adding 3 new artifact types creates O(n^2) potential trace direction pairs. If all are added eagerly, the `VALID_TRACE_DIRECTIONS` set becomes unmanageable and hard to validate.

**Why real now:** P0/P1 has 14 valid trace directions for 6 types. Adding MODE, TRANS, GUARD creates up to 9 types × 8 targets × k link_types potential entries.

**Consequence:** Trace validation becomes too permissive (accepts meaningless traces) or too restrictive (rejects valid engineering relationships). Either way, traceability loses its value.

**Mitigation:**
- Only add trace directions that have concrete engineering justification from the demo scenarios
- Start with the minimum set listed in §4 (~10 new directions) and extend only when a real need is demonstrated
- Each new `VALID_TRACE_DIRECTIONS` entry must have a comment explaining its engineering rationale
- Gate P2-E verifies that existing traces are unaffected

---

### Risk R4: Execution/Validation Logic Coupling

**Description:** The `mode_graph.py` service and `mode_validator.py` become entangled, making it impossible to validate a graph without also simulating it, or to simulate without running all validation.

**Why real now:** Both modules operate on the same in-memory graph. The temptation is to put reachability analysis (which is validation) and transition firing (which is execution) in the same class.

**Consequence:** Phase 3 simulation engine cannot be built without refactoring Phase 2 validation. Validators become order-dependent on execution state.

**Mitigation:**
- `mode_graph.py` is a pure data structure: build graph, expose read-only queries (reachable_from, dead_transitions, etc.)
- `mode_validator.py` is a consumer: it queries the graph and produces issue reports. It does NOT modify the graph.
- No "execution" or "step" methods in Phase 2. The graph is static. Phase 3 will introduce a separate `ModeExecutor` that takes a `ModeGraph` as input.
- Enforce this separation with a code review checkpoint in Phase 2B.

---

### Risk R5: Premature Implementation Dirties Phase 2

**Description:** Eagerness to "show progress" leads to implementing too much too fast — partial execution engine, half-built CLI, untested validators — creating technical debt that's harder to fix than to do right.

**Why real now:** The project has momentum from v4.1 closure. The temptation is to jump directly into coding a full state machine engine.

**Consequence:** Buggy validators give false confidence. Incomplete CLI commands create documentation mismatches. Partially implemented features become maintenance burden.

**Mitigation:**
- Strict phase gating: Phase 2A must pass before 2B starts; 2B before 2C; etc.
- Each phase has explicit "does NOT include" constraints
- `python -m pytest` must pass at every checkpoint with zero regressions
- No CLI command ships without at least one integration test using `tmp_path` + real subprocess

---

### Risk R6: Formal Baseline Population Delay

**Description:** The formal `artifacts/` root remains empty indefinitely, meaning Phase 2 only ever runs against demo data. Phase 2 tools may develop subtle demo-only assumptions.

**Why real now:** Formal baseline population is a separate activity not controlled by Phase 2 planning. There is no timeline for it.

**Consequence:** Phase 2 validators are only tested against the tiny demo graph (3 modes, 3 transitions, 2 guards). Edge cases in larger graphs (priority conflicts, deep nesting, large ABN sets) are never exercised.

**Mitigation:**
- Phase 2B tests MUST use synthetic `tmp_path` data with adversarial cases (10+ modes, priority collisions, unreachable states, dangling guards)
- Do not assume demo-scale complexity is sufficient for validation testing
- Document in Phase 2 handoff that formal baseline population should ideally begin during or immediately after Phase 2C

---

## 9. Phase 2 Implementation Prompt Skeleton

```
【会话名】
APLH-Phase2A-Exec

【负责模型】
Opus 4.6

【角色定义】
你是 APLH Phase 2A 的实施执行器。
你的唯一任务是实现 Phase 2A：新 artifact schema + trace extension。
你不是规划者（规划已完成，见 docs/PHASE2_ARCHITECTURE_PLAN.md）。
你不能修改 P0/P1 gate 逻辑。
你不能宣布 Phase 2 已完成。

【唯一目标】
实现 Phase 2A 交付物并通过 Gate P2-A 和 Gate P2-E。

【输入上下文】
- 架构规划：docs/PHASE2_ARCHITECTURE_PLAN.md §4（新 artifact 设计）
- 现有模型参考：aero_prop_logic_harness/models/common.py, requirement.py, trace.py
- 现有加载器：aero_prop_logic_harness/loaders/artifact_loader.py
- 现有注册表：aero_prop_logic_harness/services/artifact_registry.py
- 路径常量：aero_prop_logic_harness/path_constants.py

【交付物】
1. models/mode.py — MODE Pydantic 模型（含 incoming_transitions, outgoing_transitions §2.7）
2. models/transition.py — TRANS Pydantic 模型
3. models/guard.py — GUARD Pydantic 模型（含 used_by_transitions §2.7；含结构化 predicate §4.9）
4. models/predicate.py — AtomicPredicate / CompoundPredicate Pydantic 模型（§4.9 语法）
5. 扩展 common.py: ArtifactType, PREFIX_TO_TYPE, ID_PATTERN
6. 扩展 trace.py: TraceLinkType, VALID_TRACE_DIRECTIONS（不含 TRANS→IFACE §4.6，不含 TRANS→FUNC §4.8）
7. 扩展 artifact_loader.py: PREFIX_TO_DIRECTORY, _get_model_class()
8. 扩展 P0/P1 模型: requirement.py, function.py, interface.py, abnormal.py — 添加 §2.6 定义的 9 个 additive fields（全部 list[str] 默认 []）
9. 扩展 models/__init__.py: 导出新类型
10. JSON schema 导出（scripts/dump_schemas.py）
11. YAML 模板（templates/mode.template.yaml 等）
12. 单元测试（tests/test_phase2_models.py）+ P0/P1 模型回归测试 + predicate grammar 解析测试

【Gate 通过条件】
- python -m pytest 退出 0，零回归
- 新 artifact 可被 load_artifact() 正确加载
- 无效 artifact 被 Pydantic 正确拒绝（含 predicate 语法违规）
- 现有 11 条 demo trace 仍通过验证
- validate-artifacts --dir artifacts/examples/minimal_demo_set 仍退出 0
- Gate P2-E 仅检查 E1–E4（E5 属于 Phase 2B）
- GUARD.predicate 使用 §4.9 结构化语法，不是自由字符串
- GUARD 是条件表达式的唯一机器可检查权威（§4.7）
- TRANS.actions 不纳入 consistency scope（§4.8）
- 所有 gate 项必须标注治理等级 T1/T2/T3（§6.0）

【边界 / 禁止事项】
- 不要实现 mode_graph.py（Phase 2B）
- 不要实现 mode_validator.py（Phase 2B）
- 不要扩展 ConsistencyValidator（Phase 2B，P2-E5）
- 不要创建 demo Phase 2 artifact 数据（Phase 2C）
- 不要添加新 CLI 命令（Phase 2B）
- 不要修改 freeze-readiness 逻辑
- 不要修改 path_constants.py（已经够用）
- 不要添加 TRANS→IFACE trace direction（§4.6 决策：field-only）
- 不要添加 TRANS→FUNC trace direction（§4.8 决策：field-only，不进 consistency scope）
- 不要在 predicate 里实现 evaluator 或 DSL 解释器（§4.9 只做结构验证）
- 不要破坏任何现有测试
```

---

## 10. Final Recommendations

### 10.1 Next session assignment

| Phase | Recommended session name | Recommended model | Rationale |
|---|---|---|---|
| Phase 2A (schema) | `APLH-Phase2A-Exec` | **Opus 4.6** | Schema design requires deep structural reasoning and consistency with existing P0/P1 models (MODEL_ROUTING_POLICY.md §3.1) |
| Phase 2B (validators) | `APLH-Phase2B-Exec` | **Opus 4.6** | Graph algorithm implementation and adversarial test design require strong reasoning |
| Phase 2C (demo data) | `APLH-Phase2C-Exec` | **Opus 4.6** or **GPT-5.4** | Data authoring is more routine; GPT-5.4 sufficient if schema is stable |
| Phase 2D (docs/handoff) | `APLH-Phase2D-Exec` | **GPT-5.4** | Documentation writing; lower complexity |
| Phase 2 review | `APLH-Phase2-Review` | **Opus 4.6** or separate human reviewer | Gate verification requires same depth as implementation |

### 10.2 Recommended next action

1. Submit this planning document for human review.
2. If approved, launch `APLH-Phase2A-Exec / Opus 4.6` with the prompt skeleton from §9.
3. After Phase 2A passes Gate P2-A + P2-E, proceed to Phase 2B.
4. Do not skip phases. Do not parallelize Phase 2B and 2C.

### 10.3 What this document does NOT authorize

- It does not declare formal baseline frozen.
- It does not declare Phase 2 implemented.
- It does not modify any P0/P1 gate status.
- It does not create any new code files (planning only).

---

*End of APLH Phase 2 Architecture Planning Package.*
