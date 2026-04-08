# Conventions

## Artifact and Document Identity

- Artifact ids use typed prefixes such as `REQ-`, `FUNC-`, `IFACE-`, `ABN-`, `MODE-`, `TRANS-`, `TRACE-`
- Governance docs use explicit document ids and version headers
- Post-Phase7 governance work uses long, descriptive document names to preserve review traceability

## Repository Truth Rules

- Repository files are canonical
- Notion only stores summaries, pointers, statuses, and execution control metadata
- Accepted reports are not casually rewritten; new work should create new bounded packages

## GSD Conventions For This Repo

- `.planning/` tracks only the remaining automation and freeze-side governance path
- Phase 12 records the cockpit bootstrap that happened in this session
- Phase 13 onward is the active/future execution chain
- Manual Opus 4.6 reviews are modeled as explicit review-gate phases, not implicit comments

## Operational Conventions

- Stop automation at every explicit Opus review gate
- Never imply `accepted_for_review` equals `freeze-complete`
- Never write `freeze_gate_status.yaml` during request-package or docs-only work
- Treat current failing tests as visible blockers, not invisible debt
