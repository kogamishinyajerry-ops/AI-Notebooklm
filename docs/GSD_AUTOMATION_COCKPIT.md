# GSD Automation Cockpit

This document explains how `AI ControlLogicMaster` now uses GSD plus Notion as a resumable development cockpit.

## Control Model

- Notion = control plane
- `.planning/` = executable memory and GSD state
- Repository = source of truth for code, evidence, docs, and accepted reports
- Opus 4.6 = explicit manual review gate
- Later freeze authority = terminal manual boundary

## What Is Automated

- Current project state and next action live in Notion and `.planning/`
- Brownfield codebase context is written into `.planning/codebase/`
- Remaining roadmap is structured as executable GSD phases
- Current plan files can be executed without rebuilding prompts manually
- Notion cockpit can be synchronized from local state
- Cockpit sync re-discovers moved pages and child databases before updating cached ids
- `python scripts/gsd_cockpit.py status` exposes the current resume point for automation runners

## What Is Not Automated

- Triggering Opus 4.6 review
- Final freeze-authority write to `freeze_gate_status.yaml`
- Implicitly resolving failing tests or hidden blockers

## Operating Loop

1. Open the Notion cockpit.
2. Read `Projects`, `Session Briefs`, and `Work Items`.
3. Read `.planning/STATE.md`.
4. If current phase is an execution phase, run the next plan.
5. If current phase is a review gate, stop and wait for the user to trigger Opus 4.6.
6. Ingest review result, sync Notion, and continue to the next phase.

## Current Remaining Phases

- Phase 13: Checklist completion request package
- Phase 14: Opus 4.6 review gate
- Phase 15: Docs-only checklist completion action
- Phase 16: Opus 4.6 review gate
- Phase 17: Final freeze-signoff request package
- Phase 18: Opus 4.6 review gate
- Phase 19: Manual freeze-authority handoff

## Known Limits

- The workspace is now a git-backed repository on `main`, tracking `origin/main` at `https://github.com/kogamishinyajerry-ops/kogamishinyajerry-ops`.
- `pytest` is not fully green, so repo health must be treated as partially blocked.

## Sync Commands

Local planning and Notion hub:

```bash
python scripts/notion_control_hub.py sync
python scripts/gsd_cockpit.py sync
python scripts/gsd_cockpit.py status
```
