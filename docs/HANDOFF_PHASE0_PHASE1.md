# Handoff: Phase 0 & Phase 1 — AeroProp Logic Harness

**Document ID:** APLH-ARCH-002  
**Status:** REQUIRED FOR PHASE 2 ENTRY  

---

## 1. Current State (Phase 0 + Phase 1 Completed)

The **Phase 0 (Governance)** and **Phase 1 (Knowledge Foundation)** objectives have been successfully implemented. The repository now establishes a clean, local-first engineering foundation.

### 1.1 Completed Items
- **Governance Setup:** Project boundaries, explicit assumptions, and non-goals are strictly defined. AI authority boundaries and trust levels are documented.
- **Review Gates:** Formal checklists created for schema, data, and baseline freezes.
- **Model Routing Policy:** Guidelines established for directing specific engineering tasks to GPT-5.4, Gemini 3.1 Pro, Opus 4.6, or Minimax 2.7.
- **Artifact Models:** Five core engineering artifacts (REQ, FUNC, IFACE, ABN, TERM) defined as Pydantic models.
- **Traceability Skeleton:** Directed, typed trace links enabled with consistency rules.
- **Templates & Schemas:** YAML templates and JSON Schemas generated for all types.
- **CLI & Validators:** Typer CLI implemented with commands for schema validation, cross-reference checking, and freeze readiness assessment.
- **Minimal Demo Set:** 5 examples demonstrating realistic (but non-proprietary) engine overspeed protection logic.
- **Testing:** `pytest` suite running clean on ID rules, schema logic, and example data consistency.

### 1.2 Uncompleted / Deferred Items
- **State Machine Execution:** Deferred to Phase 2.
- **Simulation / Test Scenarios:** Deferred to Phase 2.
- **Change Impact Analysis Engine:** Deferred to Phase 2+.
- **UI / Dashboard:** Deferred to Phase 3.

## 2. Key Design Decisions Made

1. **Pydantic as Single Source of Truth:** We do not write JSON schemas by hand. Pydantic models in Python define the schema, and JSON schemas are exported from them via `dump_schemas.py`.
2. **Strict File/Folder Convention:** Everything maps via `PREFIX-NNNN.yaml`. This avoids needing complex metadata indices or DB tables. 
3. **Trace Links vs. Embedded Arrays:** Both exist. Embedded arrays (e.g., `linked_functions`) are fast lookup helpers. Dedicated `TraceLink` (TRACE-xxxx) files carry the *rationale*, *confidence*, and *directionality* of the complex relationships.
4. **No External DB:** Kept entirely file-based to make Git the sole versioning authority and simplify cross-team file sharing.
5. **Human Gate Enforcement via Schema:** The `confidence` and `review_status` fields are mandatory in the underlying `Provenance` model.

## 3. Risks and Recommendations

- **Risk - Schema Evolution:** The domain logic is immensely complex. While Phase 1 models are robust for general logic, engine-specific timing properties or data bus constraints might force schema modifications.
  - *Recommendation:* Do not subclass the models heavily. Keep them flat. Append new optional fields rather than breaking old ones.
- **Risk - Traceability Graph Explosion:** With thousands of artifacts, generating trace reports natively in Python might get slow.
  - *Recommendation:* The CLI `check-trace` is unoptimized (O(N) iteration). If artifact count crosses ~1000, move the in-memory `ArtifactRegistry` to use a lightweight `networkx` graph.
- **Risk - AI Prompting:** As engineers start using Gemini/Opus to digest manuals, they may try to pipe AI output directly into `artifacts/`.
  - *Recommendation:* Enforce the rule that AI extracted data MUST have `review_status: draft` and `confidence < 0.8`. The CLI `freeze-readiness` command will intercept improperly frozen AI data.

## 4. Advice for the Phase 2 Execution Engineer

When you begin Phase 2 (State Machine Engine):
1. **Do not modify the Phase 1 schema** unless absolutely necessary. Build *new* artifacts (e.g., `STATE-xxxx`, `TEST-xxxx`) and link them to `FUNC-xxxx`.
2. Do not introduce a database. Keep using the filesystem.
3. The next major step is defining how a `Function` implements a finite state machine. Create `aero_prop_logic_harness/models/state_machine.py` mirroring the style of `requirement.py`.
4. Ensure your new logic engine can ingest the `ArtifactRegistry` memory graph. 
5. Start small: implement an execution engine that only handles the `FUNC-0001` (Overspeed Detection) state transition.

Good luck.
