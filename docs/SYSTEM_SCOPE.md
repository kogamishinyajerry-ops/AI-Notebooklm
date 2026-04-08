# System Scope — AeroProp Logic Harness

**Document ID:** APLH-GOV-002  
**Version:** 0.1.0  
**Status:** DRAFT — Pending Gate A Freeze  

---

## 1. System Identity

**AeroProp Logic Harness (APLH)** is a local-first, schema-driven engineering knowledge management system for civil aviation propulsion control logic.

**System type:** Development-aid / review-aid / knowledge-engineering / verification-aid  

## 2. What This System IS

| Capability | Description |
|---|---|
| Structured artifact store | YAML/JSON files with defined schemas for requirements, functions, interfaces, abnormals, glossary |
| Traceability engine | Explicit typed links between artifacts with consistency validation |
| Validation toolchain | CLI-driven schema validation, ID checking, cross-reference verification |
| Review gate framework | Defined checkpoints with entry criteria and pass/fail assessment |
| Provenance tracker | Source attribution, confidence scoring, and review status for every artifact |
| Knowledge organization aid | Structured templates and models to support engineering knowledge capture |

## 3. What This System IS NOT

| Excluded Capability | Boundary Rationale |
|---|---|
| Certified airborne software (DO-178C) | APLH is tooling, not target software |
| Airworthiness compliance evidence | APLH supports review preparation but is not the evidence itself |
| Original requirement source | Requirements must originate from engineering authority, not AI |
| Real-time control system | No embedded code, no hardware interface |
| Production database | File-based by design; no SQL/NoSQL dependency |
| Autonomous decision maker | All outputs advisory; human-in-the-loop mandatory |

## 4. System Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                    APLH BOUNDARY                        │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Artifacts│  │Validators│  │  CLI     │              │
│  │ (YAML)   │  │(Python)  │  │(typer)   │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│  ┌────┴──────────────┴──────────────┴────┐              │
│  │         Schema Layer (Pydantic)       │              │
│  └───────────────────────────────────────┘              │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Schemas  │  │Templates │  │  Docs    │              │
│  │ (JSON)   │  │ (YAML)   │  │ (MD)     │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
         ▲                              │
         │ inputs                       │ outputs
         │                              ▼
  ┌──────────────┐            ┌──────────────────┐
  │ Engineering  │            │ Validation reports│
  │ source docs  │            │ Trace matrices    │
  │ (external)   │            │ Freeze checklists │
  └──────────────┘            └──────────────────┘
```

## 5. Input Sources and Trust Levels

| Source | Trust Level | Treatment |
|---|---|---|
| Published regulations (CCAR, FAR, CS-E) | Trusted reference | Cite with document ID; treat as authoritative |
| OEM design documents | Trusted primary source | Cite with document ID and version |
| Engineering team decisions | Trusted primary source | Record with author and date |
| Published textbook / standard references | Trusted reference | Cite with full reference |
| AI-extracted content | Candidate knowledge only | Must carry `provenance.method = "ai_extracted"`, `review_status = "draft"` |
| AI-inferred content | Candidate knowledge only | Must carry `provenance.method = "ai_inferred"`, `confidence < 0.7`, `review_status = "draft"` |
| Cross-project analogies | Candidate knowledge only | Must be explicitly marked as analogy, not fact |

## 6. Phase Scope Matrix

| Capability | Phase 0 | Phase 1 | Phase 2 | Phase 3+ |
|---|---|---|---|---|
| Governance docs | ✅ | — | — | — |
| Schema definitions | ✅ | ✅ | Extend | Extend |
| Data models (Pydantic) | — | ✅ | Extend | Extend |
| Templates | — | ✅ | Extend | Extend |
| Example data | — | ✅ | Extend | Extend |
| Validators | — | ✅ | Extend | Extend |
| CLI | Skeleton | Basic | Extended | Extended |
| Traceability | — | Basic | Full matrix | Impact analysis |
| State machine engine | — | — | ✅ | Extend |
| Abnormal reasoning | — | — | ✅ | Extend |
| Test generation | — | — | — | ✅ |
| UI / Dashboard | — | — | — | ✅ |

## 7. Deployment Context

- **Runtime:** Python 3.11+ on local workstation
- **Storage:** Local filesystem (YAML, JSON, Markdown files)
- **Version control:** Git (assumed)
- **CI/CD:** Not required for Phase 0–1; pytest sufficient
- **Network dependency:** None for core operations
- **Cloud services:** None required

---

*This document is subject to Gate A (Boundary Freeze) review.*
