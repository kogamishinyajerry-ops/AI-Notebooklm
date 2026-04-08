# Artifact Model — AeroProp Logic Harness

**Document ID:** APLH-GOV-004  
**Version:** 0.2.0  
**Status:** DRAFT — Updated for Phase 2A  

---

## 1. Overview

An **artifact** in APLH is a structured, versioned, traceable unit of engineering knowledge. All artifacts share a common metadata envelope and are stored as individual YAML files in the `artifacts/` directory tree.

## 2. Artifact Types

| Type Code | Artifact Type | Directory | Description |
|---|---|---|---|
| `requirement` | Requirement | `artifacts/requirements/` | Structured engineering requirement statement |
| `function` | Function | `artifacts/functions/` | Functional decomposition entry |
| `interface` | Interface | `artifacts/interfaces/` | Logical interface specification |
| `abnormal` | Abnormal | `artifacts/abnormals/` | Abnormal/failure condition description |
| `glossary_entry` | Glossary Entry | `artifacts/glossary/` | Terminology definition |
| `trace_link` | Trace Link | `artifacts/trace/` | Directed traceability link between artifacts |
| `mode` | Mode | `artifacts/modes/` | Operating mode definition (Phase 2A) |
| `transition` | Transition | `artifacts/transitions/` | State transition between modes (Phase 2A) |
| `guard` | Guard | `artifacts/guards/` | Boolean predicate guarding a transition (Phase 2A) |

## 3. Common Metadata Envelope

All artifact types (except trace_link, which has its own structure) carry these common fields:

```yaml
# === Common Metadata (present in all artifacts) ===
id: ""              # Unique artifact ID, see ID_AND_NAMING_CONVENTIONS.md
artifact_type: ""   # One of: requirement, function, interface, abnormal, glossary_entry, mode, transition, guard
version: "0.1.0"    # Semantic version of this artifact
status: "draft"     # Lifecycle status: draft | active | deprecated | withdrawn
provenance:
  source_type: ""   # human_authored | ai_extracted | ai_inferred | mixed | reference
  source_refs: []   # List of source document references
  method: ""        # How this content was produced
  confidence: 0.5   # 0.0–1.0, see ASSUMPTIONS_AND_BOUNDARIES.md §3
  reviewed_by: ""   # Reviewer identity (empty if not yet reviewed)
  review_date: ""   # ISO date of review (empty if not yet reviewed)
review_status: "draft"  # draft | in_review | reviewed | frozen | rejected
tags: []            # Free-form tags for filtering/grouping
created_at: ""      # ISO 8601 timestamp
updated_at: ""      # ISO 8601 timestamp
notes: ""           # Free-text notes, assumptions, open questions
```

## 4. Artifact Lifecycle

```
  draft ──► in_review ──► reviewed ──► frozen
    │           │             │
    │           ▼             │
    │       rejected          │
    │           │             │
    ▼           ▼             ▼
  deprecated   (revise)    (new version required for changes)
```

- **draft**: Work in progress; may be incomplete
- **in_review**: Submitted for human review; should not be modified during review
- **reviewed**: Human reviewer has approved; ready for potential freeze
- **frozen**: Part of a baselined set; changes require a new version
- **rejected**: Review found issues; must be revised (returns to draft)
- **deprecated**: Superseded by a newer artifact; retained for history

## 5. Storage Conventions

- Each artifact is a single YAML file
- Filename matches the artifact ID in lowercase: `{id}.yaml` (e.g., `req-0001.yaml`)
- One artifact per file (no multi-document YAML)
- Files are organized by type in the `artifacts/` directory tree
- Trace links may be stored as individual files or batched per source artifact

## 6. Provenance Rules

| `provenance.source_type` | `confidence` Range | Can Be Frozen? | Requires Review? |
|---|---|---|---|
| `human_authored` | 0.8–1.0 typical | Yes | Yes |
| `reference` | 0.9–1.0 typical | Yes | Yes |
| `ai_extracted` | 0.3–0.8 typical | Only after review | Mandatory |
| `ai_inferred` | 0.1–0.6 typical | Only after review + upgrade | Mandatory |
| `mixed` | Varies | Only after review | Mandatory |

## 7. Phase 2A Additions

Phase 2A implements the MODE/TRANSITION/GUARD artifact layer:

- **Mode**: Operating mode with hierarchy (`parent_mode`), reciprocal transition links, and P0/P1 cross-references
- **Transition**: Directed state change with source/target modes, guard condition, priority arbitration
- **Guard**: Boolean predicate using structured grammar (`AtomicPredicate | CompoundPredicate`). The `predicate` field is the sole machine-checkable authority (§4.7)

Phase 2A also adds optional additive fields to P0/P1 models (`linked_modes`, `linked_transitions`, etc.) and extends the trace skeleton with 11 new directions.

See `PHASE2A_IMPLEMENTATION_NOTES.md` for full details.

## 8. Extension Points for Phase 2B+

The following are anticipated but NOT implemented yet:

- `ConsistencyValidator` reverse-loop enforcement for Phase 2 types (Phase 2B)
- Mode graph construction and topological validation (Phase 2B)
- `validate-modes` CLI command (Phase 2B)
- Demo artifact authoring for Phase 2 types (Phase 2C)
- Predicate evaluator / semantic execution engine (Phase 3+)
- `certification_mapping`: DO-178C/ARP-4754A data item cross-reference (Phase 3+)

These are documented here to guide design but must NOT be implemented prematurely.

---

*This document is subject to Gate B (Schema Freeze) review.*
