# Project Charter — AeroProp Logic Harness (APLH)

**Document ID:** APLH-GOV-001  
**Version:** 0.1.0  
**Status:** DRAFT — Pending Gate A Freeze  
**Last Updated:** 2026-04-02  

---

## 1. Project Purpose

The AeroProp Logic Harness (APLH) is an engineering knowledge harness designed to support civil aviation propulsion system control logic development. It provides a structured, traceable, and reviewable framework for organizing and validating:

- Control system requirements
- Functional decomposition
- Operating-condition trigger logic
- Mode / state transition logic
- Interface constraints
- Abnormal / failure handling logic
- Verification scenarios
- Change impact analysis preparation
- Review evidence packaging

The harness serves as an **engineering development aid** — it structures, traces, and validates the logical artifacts that propulsion control engineers create and review during the design process.

## 2. Non-Goals (Out of Scope)

The following are **explicitly excluded** from this project's scope:

| Excluded Item | Rationale |
|---|---|
| Certified airborne software | APLH is not DO-178C target code |
| Airworthiness compliance demonstration | APLH aids review but does not constitute compliance evidence |
| Autonomous requirement generation | AI may extract/organize/compare but cannot be the original requirement source |
| Real-time embedded control code | No target hardware code generation |
| Production database systems | Local-first file-based approach |
| Customer-facing UI/dashboard (Phase 0–1) | Deferred to Phase 3+ |
| State machine execution engine | Deferred to Phase 2 |
| Automatic test case generation | Deferred to Phase 2+ |
| Vector search / semantic retrieval | Deferred; if needed, Phase 3+ |

## 3. User Personas

### 3.1 Primary: Propulsion Control Systems Engineer
- Creates and reviews control logic requirements
- Defines functional decomposition and interface specifications
- Needs structured, traceable artifact management
- Needs quick validation of artifact consistency

### 3.2 Secondary: Review / Audit Personnel
- Reviews artifact sets for completeness and consistency
- Needs clear provenance and confidence metadata
- Needs evidence of review gate compliance
- Needs exportable review packages

### 3.3 Future: AI-Assisted Workflow Operator
- Uses AI models to assist with extraction, comparison, gap analysis
- Needs clear routing rules for which AI model handles which task
- Needs provenance tracking for all AI-generated content

## 4. Core Values

1. **Traceability**: Every artifact traces to its sources and related artifacts
2. **Auditability**: Every item carries provenance, confidence, and review status
3. **Local-first**: All data lives as local files; no cloud dependency for core operations
4. **Schema-first**: Data models are defined before data is created
5. **Minimal but extensible**: Current scope is lean; future phases can extend without restructuring
6. **Human-in-the-loop**: AI assists but humans decide; all AI output requires review

## 5. Current Phase Objectives

### Phase 0 — Governance & Foundation
- Establish project boundaries, assumptions, and review gates
- Define artifact model, ID conventions, and naming rules
- Create schema skeleton for all core artifact types
- Define model routing policy for multi-AI workflow

### Phase 1 — Knowledge Foundation
- Implement data models for Requirement, Function, Interface, Abnormal, Glossary
- Create JSON schemas, YAML templates, and minimal example datasets
- Build basic validation and consistency checking tools
- Establish traceability skeleton with schema, sample data, and checker
- Implement provenance and confidence governance mechanism

## 6. Risks & Constraints

| Risk / Constraint | Mitigation |
|---|---|
| Domain knowledge gaps in automated tooling | All assumptions documented explicitly; conservative defaults |
| Schema may need revision as real data is ingested | Version field in all artifacts; migration notes in handoff docs |
| AI-generated content quality varies | Provenance + confidence + review_status fields enforce human gate |
| Single-engineer execution risk | Comprehensive handoff documentation; self-contained artifacts |
| Over-engineering risk | Strict phase boundaries; "no fake completeness" principle |

## 7. Success Criteria

Phase 0 + Phase 1 is considered successful when:

- [ ] All governance documents written and internally consistent
- [ ] All five artifact type schemas are defined and machine-validatable
- [ ] Minimal example dataset passes all validators
- [ ] Traceability links are expressible, storable, and checkable
- [ ] CLI can validate artifacts, check traces, and assess freeze-readiness
- [ ] All tests pass
- [ ] Handoff document is complete and actionable
- [ ] No unresolved blocking issues remain for Phase 2 entry

---

*This document is subject to Gate A (Boundary Freeze) review.*
