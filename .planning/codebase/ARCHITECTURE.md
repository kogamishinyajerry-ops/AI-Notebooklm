# Architecture

## System Shape

APLH is a schema-first, local-first Python CLI. The codebase is organized around three layers:

1. **Models**
   Pydantic definitions for requirements, functions, interfaces, guards, modes, transitions, scenarios, promotion artifacts, and freeze status.

2. **Services**
   Runtime orchestration for graph loading, evaluation, promotion, formal population, audit correlation, freeze-review preparation, and readiness assessment.

3. **Validators**
   Schema, trace, consistency, coverage, and mode validation over artifact sets.

## Data Plane

- Canonical engineering artifacts live in `artifacts/`
- Governance state lives under `artifacts/.aplh/`
- Example/demo-scale sets live under `artifacts/examples/`
- Trace graph and review evidence are file-based, not database-backed

## Execution Plane

- CLI entrypoint is [`aero_prop_logic_harness/cli.py`](/Users/Zhuanz/20260402%20AI%20ControlLogicMaster/aero_prop_logic_harness/cli.py)
- Registry loads artifacts from disk and validators/services operate over that in-memory graph
- Freeze readiness is intentionally separate from final freeze declaration

## Control Plane

- Notion hub is the process control plane
- `.planning/` is the GSD execution memory
- Repository remains the source of truth for code, evidence, and accepted docs

## Current Architectural Boundary

The active work is no longer core subsystem implementation. It is governance-side continuation:

- checklist/docs completion
- bounded request packages
- Opus 4.6 review pauses
- later manual freeze-authority handoff
