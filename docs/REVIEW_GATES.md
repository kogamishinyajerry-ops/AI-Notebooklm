# Review Gates — AeroProp Logic Harness

**Document ID:** APLH-GOV-006  
**Version:** 0.1.0  
**Status:** DRAFT  

---

## 1. Purpose

Review gates are defined checkpoints that must be passed before the project advances to the next phase or freezes a baseline. Each gate is manually executed by a human reviewer using this document as a checklist.

**Governance principle:** No gate can be passed by AI alone. AI may assist in preparing gate evidence, but the pass/fail decision is a human responsibility.

## 2. Gate Definitions

---

### Gate A — Boundary Freeze

**Objective:** Confirm that project scope, boundaries, assumptions, and governance rules are stable enough to build upon.

**Input Conditions:**
- `docs/PROJECT_CHARTER.md` exists and is complete
- `docs/SYSTEM_SCOPE.md` exists and is complete
- `docs/ASSUMPTIONS_AND_BOUNDARIES.md` exists and is complete

**Check Items:**

| # | Check | Pass Criterion |
|---|---|---|
| A1 | Project purpose is clearly stated | Unambiguous single-paragraph purpose |
| A2 | Non-goals are explicitly listed | At least 5 explicit exclusions |
| A3 | User personas are identified | At least 2 personas with role descriptions |
| A4 | System boundary diagram exists | Text or graphical boundary diagram present |
| A5 | Trust levels for input sources are defined | Table with ≥4 source types and trust levels |
| A6 | AI authority boundaries are defined | Explicit "may/may not" rules for AI |
| A7 | Assumptions are numbered and reviewable | Each assumption has an ID (A1.x format) |
| A8 | Phase scope matrix exists | Table showing capability × phase mapping |

**Common Failure Modes:**
- Scope statement too vague or too broad
- Missing non-goals (leading to scope creep)
- AI authority rules not specific enough
- Trust levels not actionable

---

### Gate B — Schema Freeze

**Objective:** Confirm that artifact data models, ID conventions, and schemas are stable for data entry to begin.

**Input Conditions:**
- Gate A passed
- `docs/ARTIFACT_MODEL.md` exists and is complete
- `docs/ID_AND_NAMING_CONVENTIONS.md` exists and is complete
- All JSON schemas exist in `schemas/`
- All Pydantic models exist in `aero_prop_logic_harness/models/`

**Check Items:**

| # | Check | Pass Criterion |
|---|---|---|
| B1 | All 5 artifact types have schemas | JSON schema files exist for requirement, function, interface, abnormal, glossary_entry |
| B2 | Trace link schema exists | `trace_link.schema.json` present and valid |
| B3 | Common metadata fields are consistent | Same envelope across all types |
| B4 | ID format regex is defined and implemented | Regex in docs matches validator code |
| B5 | File naming rules are defined | Rules in docs match actual file layout |
| B6 | Provenance/confidence rules are defined | Table with source_type → confidence → freeze eligibility |
| B7 | Lifecycle states are defined | State diagram with transitions documented |
| B8 | Templates exist for all artifact types | `.template.yaml` files in `templates/` |

**Common Failure Modes:**
- Schema fields inconsistent across types (e.g., `source_refs` vs `references`)
- ID regex not matching between docs and code
- Missing required fields in schema but not enforced
- Template missing field descriptions

---

### Gate C — Example Data Passes

**Objective:** Confirm that the minimal example dataset is valid, loads correctly, and demonstrates the intended artifact relationships.

**Input Conditions:**
- Gate B passed
- Example artifacts exist in `artifacts/examples/` or `examples/minimal_demo_set/`
- Validators are implemented

**Check Items:**

| # | Check | Pass Criterion |
|---|---|---|
| C1 | Example requirements load without errors | `aplh validate-artifacts` passes |
| C2 | Example functions load without errors | All FUNC artifacts valid |
| C3 | Example interfaces load without errors | All IFACE artifacts valid |
| C4 | Example abnormals load without errors | All ABN artifacts valid |
| C5 | Example glossary entries load without errors | All TERM artifacts valid |
| C6 | Example trace links are valid | `aplh check-trace` passes |
| C7 | Cross-references resolve | No dangling references in linked_* fields |
| C8 | Provenance/confidence values are plausible | No `confidence: 1.0` on `ai_inferred` content |

**Common Failure Modes:**
- Example data created but never validated
- Trace links reference non-existent IDs
- Confidence values inconsistent with source_type
- Missing required fields in example artifacts

---

### Gate D — Traceability Skeleton Passes

**Objective:** Confirm that the traceability mechanism works end-to-end: links are expressible, storable, loadable, and checkable.

**Input Conditions:**
- Gate C passed
- Trace model and schema implemented
- Trace validator implemented
- Example trace links exist

**Check Items:**

| # | Check | Pass Criterion |
|---|---|---|
| D1 | REQ → FUNC traces exist in examples | At least 2 trace links |
| D2 | REQ → IFACE traces exist in examples | At least 1 trace link |
| D3 | REQ → ABN traces exist in examples | At least 1 trace link |
| D4 | FUNC → IFACE traces exist in examples | At least 1 trace link |
| D5 | ABN → FUNC traces exist in examples | At least 1 trace link |
| D6 | No dangling traces | All trace endpoints reference existing artifacts |
| D7 | Trace consistency checker runs | `aplh check-trace` produces actionable report |
| D8 | Orphan detection works | Artifacts with no incoming/outgoing traces are flagged |

**Common Failure Modes:**
- Trace links exist but point to wrong artifact type
- Trace checker passes vacuously (no links to check)
- Bidirectional consistency not verified

---

### Gate E — Formal Baseline Freeze (Freeze-Complete)

**Objective:** Confirm that all Phase 0 governance and Phase 1 knowledge foundation deliverables are populated within the formal `artifacts/` boundary and ready for handoff.

**Input Conditions:**
- Gates A through D passed
- Target directory is the formal `artifacts/` boundary.
- Target directory has a valid `.aplh/freeze_gate_status.yaml` claiming `freeze-complete` scope.
- Hermetic test command (`python -m pytest`) passes.

**Check Items:**

| # | Check | Pass Criterion |
|---|---|---|
| E1 | Baseline Boundary Defined | Signoff is formally evaluated via `python -m aero_prop_logic_harness freeze-readiness --dir artifacts` |
| E2 | All formal requirements exist | At least the required functional relations are established and reviewed |
| E3 | No drafts | All artifacts are marked `reviewed` or higher |
| E4 | All tests pass | `python -m pytest` exits 0 (Hermetic constraint) |
| E5 | Handoff document exists | `docs/HANDOFF_PHASE0_PHASE1.md` is complete |
| E6 | Not Demo Scale | Output of freeze-readiness explicitly says "✅ Ready for Formal Baseline Freeze!" |

**Common Failure Modes:**
- Passing the "demo-scale" gate but failing to populate the formal `artifacts/` boundary.
- Executing tests non-hermetically (dependent on outer shell envs).

---

## 3. Two-Tier Scope Governance (Demo VS Formal)

APLH operates under an explicit binary control surface for signoffs:

- **demo-scale:**
  Located in `artifacts/examples/minimal_demo_set/`. It is structurally complete enough to pass validations, but explicitly outputs "Demo-scale gate checks passed (Not for formal freeze)" — never "Ready for Formal Baseline Freeze".
- **freeze-complete:**
  Located at the formal baseline root `artifacts/`. It must contain the actual engineering source truth. **Programmatic enforcement:** the CLI resolves `--dir` to an absolute path and compares it against the repository's formal baseline root. A non-formal directory claiming `freeze-complete` will be rejected with a "Formal boundary violation" error regardless of what the YAML signoff states.

*All signoffs MUST be physically collocated with the artifacts they endorse inside a `.aplh/freeze_gate_status.yaml` folder schema.* They are not globals.

### `.aplh/` Control Metadata

The `.aplh/` directory contains machine-readable control metadata (signoff records, gate status). It is **not** an artifact directory. All CLI commands (`validate-artifacts`, `check-trace`, `freeze-readiness`) share a unified directory traversal (`path_constants.iter_artifact_yamls`) that excludes `.aplh/` from artifact schema validation. This prevents `.aplh/*.yaml` files from polluting schema checks.

---

## 4. Gate Execution Process

1. **Prepare:** Ensure all input conditions are met
2. **Execute Locally:** Use `python -m aero_prop_logic_harness ...` and `python -m pytest` exclusively.
3. **Record:** Modify the `.aplh/freeze_gate_status.yaml` via strict types to represent authorization.
4. **Decide:** Gate passes only if ALL items pass and CLI exits 0.
5. **Act:** Hand off to Phase 2.
