# Architecture Overview — AeroProp Logic Harness

**Document ID:** APLH-ARCH-001  
**Version:** 0.1.0  
**Status:** ACTIVE  

---

## 1. System Architecture

APLH is designed as a local-first, schema-driven Python CLI application. It eschews complex databases and web frameworks in favor of flat files and explicit schemas to maintain extreme auditability and long-term stability.

### 1.1 Module Tree

```
aero_prop_logic_harness/
├── models/             # Pydantic definitions (The Source of Truth)
│   ├── common.py       # Base artifact and provenance
│   ├── requirement.py  # REQ model
│   ├── function.py     # FUNC model
│   ├── interface.py    # IFACE model
│   ├── abnormal.py     # ABN model
│   ├── glossary.py     # TERM model
│   └── trace.py        # TRACE model
├── loaders/            # I/O layer
│   ├── yaml_loader.py      # ruamel.yaml wrapper
│   └── artifact_loader.py  # Maps YAML to Pydantic models
├── services/           # Stateful runtime services
│   └── artifact_registry.py # Cross-reference graph memory
├── validators/         # Business logic & consistency
│   ├── schema_validator.py  # File-level structural validation
│   ├── trace_validator.py   # Trace endpoint validation
│   └── consistency_validator.py # Governance rules & embedded links
└── cli.py              # Typer CLI entrypoint
```

## 2. Data Flow

1. **Ingestion**: The `ArtifactRegistry` scans the `artifacts/` tree.
2. **Parsing & Validation (Level 1)**: `yaml_loader` reads text. `artifact_loader` instantiates Pydantic models. Pydantic performs Level 1 validation (types, enums, required fields, ID regex).
3. **Graph Construction**: The Registry indexes artifacts by ID, type, and trace directionality.
4. **Consistency Checking (Level 2)**: `TraceValidator` and `ConsistencyValidator` traverse the registry graph to enforce domain rules (e.g., "Abnormal X cannot affect Interface Y if Interface Y doesn't exist" or "Artifact Z cannot be frozen if it was AI-inferred with low confidence").
5. **Reporting**: The CLI formats validation issues and freeze-readiness metrics for the engineer.

## 3. Why This Architecture? (Phase 0–1 Logic)

**Why Pydantic over pure JSON Schema?**  
Pydantic provides runtime validation and typing in Python, which is critical for writing robust validators. The JSON Schemas in `schemas/` are derivative outputs for cross-tool compatibility, but Pydantic is the master truth.

**Why flat YAML files instead of SQLite/Postgres?**  
1. Total transparency: A reviewer can read the raw data without special tools.
2. Version control: Git natively understands text diffs, enabling granular tracking of requirement evolutions.
3. No daemon: Zero dependencies on running background services.

**Why TraceLinks as separate objects rather than embedded arrays?**  
While artifacts *do* have embedded arrays for convenience (e.g., `linked_functions`), formal `TraceLink` objects carry their own metadata (rationale, confidence, authorship). A link between a requirement and a function often requires explaining *how* it's implemented, not just the fact that they are linked.

## 4. Path to Phase 2 (State Machine & Logic Engine)

The current Phase 1 foundation deliberately isolates the *knowledge graph* from execution logic.

To integrate state machine and abnormal reasoning in Phase 2:
1. **Schema Extension**: A new artifact type, `StateMachine` (e.g., `SM-xxxx`), will be introduced. `Function` artifacts will gain a `state_machine_ref` field.
2. **Logic Engine**: A new service (`engine` or `simulator`) will load state machines and use the `Interface` definitions to construct a directed execution graph.
3. **Test Generation**: Verification scenarios can be expressed as YAML injecting stimuli into `Interface` signals and asserting on `Output` signals over time.

By establishing the pure declarative schema first, Phase 2 can consume guaranteed-consistent data without having to build its own data-gathering layer.
