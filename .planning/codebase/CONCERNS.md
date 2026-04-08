# Concerns

## Immediate Concerns

- **Tests are not fully aligned with current repo reality**
  Seven failures remain, especially around historical expectations for baseline pollution, promotion manifests, and Phase 7 inventory size.

- **GitHub remote is not connected yet**
  The workspace is now a local git repository, but GitHub remote workflows still need a visible token or `gh` login.

- **Current roadmap is governance-heavy**
  Remaining work is mostly packaging, review routing, and boundary preservation rather than new subsystem implementation. The cockpit must not assume a normal feature-delivery cadence.

## Process Risks

- A future session could accidentally skip an Opus review gate unless it is explicit in both `.planning/ROADMAP.md` and Notion.
- Notion can drift from repo truth if sync is not run after roadmap or state updates.
- The current long-form governance docs are authoritative but verbose; the cockpit must keep short summaries current so future sessions stay bounded.

## What To Watch

- Whether `freeze-readiness` transitions from docs incomplete to pass after Phase 15
- Whether Phase 7 tests need a dedicated reconciliation phase before any claim of repo-wide health
- Whether GitHub remote creation should happen through `gh` once authentication is available
