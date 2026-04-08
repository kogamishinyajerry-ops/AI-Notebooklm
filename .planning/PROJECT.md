# AI ControlLogicMaster

## What This Is

AI ControlLogicMaster is the control-and-governance workspace for the AeroProp Logic Harness (APLH) repository. It combines a local-first Python CLI, an explicit `.planning/` GSD layer, and a Notion control hub so the project can progress through bounded engineering and governance steps without rebuilding session prompts by hand.

The product is already past its core implementation milestones. The active work is freeze-side governance: packaging the remaining checklist and review evidence correctly, preserving the manual boundary around final freeze signoff, and making the workflow resumable by any future Codex session.

## Core Value

Keep the project moving through auditable, bounded automation while preserving the hard manual review boundaries that protect final freeze authority.

## Requirements

### Validated

- [x] Local-first schema-driven artifact harness exists and is operational through formal population readiness.
- [x] Formal baseline can be populated, validated, traced, and classified with explicit governance evidence.
- [x] Repository contains accepted review packages and milestone documentation through Post-Phase7 final freeze signoff governance planning.
- [x] A dedicated Notion control hub now exists for AI ControlLogicMaster and is independent of AI-Harness v1/v2.

### Active

- [ ] Integrate GSD `.planning/` architecture into this brownfield repository so future sessions can resume autonomously.
- [ ] Upgrade the Notion hub into a true GSD cockpit with executable plans, review gates, and automation state.
- [ ] Complete the current bounded work item: the final freeze signoff checklist completion request package.
- [ ] Enforce a stop-and-wait review cadence where Codex pauses only at explicit Opus 4.6 review gates and later manual freeze authority gates.

### Out of Scope

- Declaring `freeze-complete` from the current automation layer — final freeze signoff remains manual-only.
- Modifying `artifacts/.aplh/freeze_gate_status.yaml` during request-package or review-package work — that would collapse the manual boundary.
- Starting Phase 8 or reopening accepted Phase 0-7 implementation boundaries — current work is governance continuation, not feature expansion.
- Treating Notion as a code or artifact source of truth — repository files remain canonical.

## Context

This repository is a mature brownfield CLI project with 50 code files under `aero_prop_logic_harness/`, 17 pytest modules, and 178 YAML artifacts. The codebase is organized around Pydantic models, validators, and services that manage schema validity, trace integrity, promotion/formal population logic, and freeze-review preparation.

Current repository truth:

- `validate-artifacts --dir artifacts` passes.
- `check-trace --dir artifacts` passes.
- `freeze-readiness --dir artifacts` fails only because checklist/docs are incomplete.
- `pytest` currently reports 311 passed / 7 failed, with failures concentrated in legacy expectations around baseline pollution, promotion manifest residue, and Phase 7 inventory counts.

The Notion control hub already exists at a dedicated page and now needs to become the control plane for GSD execution. The desired operating model is: Notion decides what is current, `.planning/` provides executable state and memory, the repository remains canonical, and Opus 4.6 reviews are explicit pause points.

## Constraints

- **Governance**: Final freeze signoff is manual-only — no automation may imply or perform `freeze-complete`.
- **Review**: Opus 4.6 review triggers must remain explicit human actions, even if surrounding planning and execution are automated.
- **Repository**: This directory is now a git-backed repository on `main`, tracking `origin/main` at `https://github.com/kogamishinyajerry-ops/kogamishinyajerry-ops`.
- **Truth Source**: Accepted docs and state files in the repository remain canonical over Notion summaries.
- **Domain Safety**: Accepted schema, trace, validator, evaluator, and runtime boundaries must not be reopened casually while building cockpit infrastructure.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use Notion as control plane, not code truth | Avoid prompt-copying while preserving repository truth | ✓ Good |
| Bootstrap GSD in-place on the current brownfield repo | Project already has rich accepted artifacts; greenfield workflow would lose context | ✓ Good |
| Treat Opus 4.6 as explicit review gates in roadmap and Notion | Makes human review pauses first-class and resumable | ✓ Good |
| Record current failing tests as blockers instead of silently fixing scope | Cockpit should surface repo reality before automating over it | ✓ Good |
| Enable planning doc commits after git initialization | Repo now has `.git`, so GSD planning artifacts can participate in atomic commits | ✓ Good |
| Connect GitHub remote after initial repo bootstrap | Enables remote backup and future PR/push workflows | ✓ Good |

---
*Last updated: 2026-04-09 after GitHub remote initialization*
