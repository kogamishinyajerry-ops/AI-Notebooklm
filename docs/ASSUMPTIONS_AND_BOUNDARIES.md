# Assumptions and Boundaries — AeroProp Logic Harness

**Document ID:** APLH-GOV-003  
**Version:** 0.1.0  
**Status:** DRAFT — Pending Gate A Freeze  

---

## 1. Explicit Assumptions

Each assumption is numbered for traceability. Assumptions marked with ⚠️ carry higher uncertainty.

### A1. Engineering Domain
- **A1.1** The primary domain is civil aviation propulsion system control logic (fuel control, thrust management, engine protection, bleed/power-offtake control, etc.)
- **A1.2** Requirements originate from system-level specifications, type design data, and regulatory requirements (CCAR-33, FAR-33, CS-E, etc.)
- **A1.3** ⚠️ The specific engine type and OEM are not fixed; the harness must remain engine-model-agnostic in its schema design
- **A1.4** Operating conditions include normal, degraded, abnormal, and emergency modes

### A2. Data Characteristics
- **A2.1** All core engineering artifacts can be meaningfully represented as structured YAML/JSON with prose fields
- **A2.2** Signal-level interface data (bus definitions, word layouts) is deferred to Phase 2+; Phase 1 captures logical interface descriptions
- **A2.3** ⚠️ Timing semantics in interface models are descriptive (e.g., "10Hz update rate"), not executable specifications
- **A2.4** Quantitative ranges in examples are illustrative, not derived from proprietary type design data

### A3. Tooling & Environment
- **A3.1** Python 3.11+ is available on the target workstation
- **A3.2** Git is used for version control
- **A3.3** No database is required; the file system is the persistence layer
- **A3.4** AI models (GPT-5.4, Gemini 3.1 Pro, Opus 4.6, Minimax 2.7) are available via API or chat interface for assisted workflows

### A4. Process & Governance
- **A4.1** A single engineer currently operates the system; multi-user concurrency is not a Phase 0–1 concern
- **A4.2** Review gates are executed manually (checklist-driven), not automated CI gates
- **A4.3** Baseline freeze is a documented decision, not an automated lock mechanism
- **A4.4** ⚠️ The relationship between APLH artifacts and formal DO-178C/ARP-4754A lifecycle data items is indirect — APLH supports preparation but does not itself constitute compliance evidence

## 2. What Phase 0–1 Explicitly Does NOT Do

| Activity | Status | Rationale |
|---|---|---|
| Generate executable control code | Not in scope, any phase | APLH is knowledge engineering, not code generation |
| Replace human requirement authoring | Forbidden | AI assists extraction/organization; humans author |
| Provide airworthiness compliance evidence | Not in scope | Separate certification process |
| Implement state machine execution | Deferred to Phase 2 | Schema-first; execution-later |
| Build abnormal reasoning engine | Deferred to Phase 2 | Need stable abnormal model first |
| Perform change impact analysis | Deferred to Phase 2 | Need full traceability first |
| Create UI dashboard | Deferred to Phase 3+ | CLI sufficient for Phase 0–1 |
| Integrate with external databases | Deferred | Local-first principle |
| Handle multi-user concurrent editing | Deferred | Single-user assumption A4.1 |

## 3. Trust and Authority Boundaries

### 3.1 What Counts as a "Trusted Source"
- Published airworthiness regulations and advisory materials
- Approved OEM design documents with explicit document IDs
- Recorded engineering decisions with identified decision-makers
- Published academic/industry references

### 3.2 What is "Candidate Knowledge" Only
- Any AI-extracted content (must be reviewed before freeze)
- Any AI-inferred content (must carry low confidence until reviewed)
- Cross-project analogies (must be explicitly labeled)
- Engineer's working notes before formal review

### 3.3 What Requires Mandatory Human Gate
- Promotion from `draft` to `reviewed` status
- Promotion from `reviewed` to `frozen` status
- Any artifact entering a baseline freeze
- Any requirement marked `safety_relevance: true`
- Any abnormal with `severity_hint: hazardous` or higher
- Deletion or major modification of frozen artifacts

### 3.4 AI Output Authority
- AI **may**: extract, organize, compare, suggest, check consistency, flag gaps
- AI **may not**: be the original source of a requirement
- AI **may not**: approve a review gate
- AI **may not**: override human-assigned review_status
- AI-generated content **must**: carry `provenance.method` indicating AI involvement
- AI-generated content **must**: carry `confidence` reflecting uncertainty
- AI-generated content **must**: start with `review_status: draft`

## 4. Naming and Terminology Boundaries

- The term "requirement" in APLH context means "a structured engineering statement captured in the harness" — it does not automatically correspond to a formal DO-178C requirement
- The term "validation" means "schema and consistency checking" — it does not mean V&V in the certification sense
- The term "freeze" means "baseline snapshot for review purposes" — it does not mean configuration-controlled in the CM sense unless explicitly stated

## 5. Data Sensitivity

- Example data in this repository is illustrative and does not contain proprietary type design data
- If real project data is loaded, appropriate access controls must be applied at the repository/filesystem level
- APLH does not implement its own access control mechanism

---

*This document is subject to Gate A (Boundary Freeze) review.*
