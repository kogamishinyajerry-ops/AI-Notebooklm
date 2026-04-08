# Concerns

## Immediate Concerns

- **No git repository**
  GSD architecture is now present, but native atomic commit behavior is unavailable until git is initialized or a no-git execution wrapper is introduced.

- **Tests are not fully aligned with current repo reality**
  Seven failures remain, especially around historical expectations for baseline pollution, promotion manifests, and Phase 7 inventory size.

- **Current roadmap is governance-heavy**
  Remaining work is mostly packaging, review routing, and boundary preservation rather than new subsystem implementation. The cockpit must not assume a normal feature-delivery cadence.

## Process Risks

- A future session could accidentally skip an Opus review gate unless it is explicit in both `.planning/ROADMAP.md` and Notion.
- Notion can drift from repo truth if sync is not run after roadmap or state updates.
- The current long-form governance docs are authoritative but verbose; the cockpit must keep short summaries current so future sessions stay bounded.

## What To Watch

- Whether `freeze-readiness` transitions from docs incomplete to pass after Phase 15
- Whether Phase 7 tests need a dedicated reconciliation phase before any claim of repo-wide health
- Whether git initialization should be adopted to unlock full stock GSD execution semantics
