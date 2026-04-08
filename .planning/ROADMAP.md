# Roadmap: AI ControlLogicMaster

## Overview

Historical APLH engineering work through Post-Phase7 final freeze signoff governance planning is already accepted. This roadmap starts from the remaining automation and freeze-side governance path: first make the repo and Notion hub GSD-native, then complete the checklist-completion request and its review/action loop, then hand off the final freeze decision to the proper manual authority.

## Phases

- [x] **Phase 12: GSD + Notion Cockpit Bootstrap** - Create the local `.planning/` layer and upgrade the Notion hub into a resumable development cockpit.
- [ ] **Phase 13: Checklist Completion Request Package** - Produce the non-executable final freeze signoff checklist-completion request package.
- [ ] **Phase 14: Opus Review - Checklist Request** - Pause for user-triggered Opus 4.6 review of the request package.
- [ ] **Phase 15: Docs-Only Checklist Completion Action** - Apply review-approved docs/checklist updates without crossing into freeze signoff.
- [ ] **Phase 16: Opus Review - Checklist Action** - Pause for user-triggered Opus 4.6 review of the docs-only action.
- [ ] **Phase 17: Final Freeze Signoff Request Package** - Prepare the later manual freeze-signoff request package once checklist evidence is complete.
- [ ] **Phase 18: Opus Review - Freeze Signoff Request** - Pause for user-triggered Opus 4.6 review of the freeze-signoff request package.
- [ ] **Phase 19: Manual Freeze Authority Handoff** - Hand over a bounded, review-cleared package to the later manual freeze authority.

## Phase Details

### Phase 12: GSD + Notion Cockpit Bootstrap
**Goal:** Make the brownfield repo fully resumable through GSD `.planning/` plus a Notion control cockpit.
**Depends on:** Historical accepted work only.
**Requirements:** REQ-GSD-01, REQ-NOTION-01, REQ-AUTO-01
**Success Criteria** (what must be TRUE):
  1. `.planning/PROJECT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json`, and `.planning/codebase/*` exist and reflect repo reality.
  2. The Notion control hub includes explicit GSD plans, review gates, and automation status.
  3. Future Codex sessions can determine the next bounded action without rebuilding prompts manually.
**Plans:** 1 plan

Plans:
- [x] 12-01: Bootstrap GSD local planning and upgrade the Notion cockpit

### Phase 13: Checklist Completion Request Package
**Goal:** Create the current non-executable checklist-completion request package and review input.
**Depends on:** Phase 12
**Requirements:** REQ-FREEZE-01, REQ-GOV-01
**Success Criteria** (what must be TRUE):
  1. The request packet distinguishes already-satisfied evidence from remaining checklist/docs gaps.
  2. The package explicitly preserves `accepted_for_review`, does not request `freeze-complete`, and does not write `freeze_gate_status.yaml`.
  3. A separate review input exists for the Opus 4.6 review gate.
**Plans:** 1 plan

Plans:
- [ ] 13-01: Draft the checklist-completion request packet and review input

### Phase 14: Opus Review - Checklist Request
**Goal:** Stop automation at a clean review gate and wait for a user-triggered Opus 4.6 review.
**Depends on:** Phase 13
**Requirements:** REQ-REVIEW-01
**Success Criteria** (what must be TRUE):
  1. The package is handed to Opus 4.6 with the correct review scope.
  2. The automation state is paused, not drifting into Phase 15.
  3. Review outcome is captured as pass / blocked / required fixes.
**Plans:** TBD

Plans:
- [ ] 14-01: Trigger Opus 4.6 review and capture result

### Phase 15: Docs-Only Checklist Completion Action
**Goal:** Apply review-approved checklist/doc updates without crossing the freeze-signoff boundary.
**Depends on:** Phase 14
**Requirements:** REQ-FREEZE-02, REQ-GOV-02
**Success Criteria** (what must be TRUE):
  1. Only docs/checklist evidence changes are made.
  2. `freeze-readiness --dir artifacts` no longer fails due to docs incomplete, or blockers are explicitly documented.
  3. No freeze-signoff state is written.
**Plans:** TBD

Plans:
- [ ] 15-01: Execute bounded docs-only checklist completion

### Phase 16: Opus Review - Checklist Action
**Goal:** Pause again for user-triggered Opus 4.6 review of the docs-only action.
**Depends on:** Phase 15
**Requirements:** REQ-REVIEW-01
**Success Criteria** (what must be TRUE):
  1. Updated docs/checklist evidence is independently reviewed.
  2. Remaining blockers, if any, are explicit and bounded.
  3. The automation loop does not advance into freeze-signoff request work without review closure.
**Plans:** TBD

Plans:
- [ ] 16-01: Trigger Opus 4.6 review for checklist action evidence

### Phase 17: Final Freeze Signoff Request Package
**Goal:** Prepare the later manual freeze-signoff request package after checklist evidence is complete.
**Depends on:** Phase 16
**Requirements:** REQ-FREEZE-03, REQ-GOV-03
**Success Criteria** (what must be TRUE):
  1. Freeze-signoff request package references complete checklist and readiness evidence.
  2. The package does not itself perform final signoff.
  3. A separate review package exists for Opus 4.6 before manual authority handoff.
**Plans:** TBD

Plans:
- [ ] 17-01: Draft the final freeze-signoff request package

### Phase 18: Opus Review - Freeze Signoff Request
**Goal:** Pause for the final user-triggered Opus 4.6 review before manual freeze-authority handoff.
**Depends on:** Phase 17
**Requirements:** REQ-REVIEW-01
**Success Criteria** (what must be TRUE):
  1. Opus 4.6 reviews the freeze-signoff request package.
  2. Review outcome is stored and linked to the handoff package.
  3. Automation does not claim freeze approval.
**Plans:** TBD

Plans:
- [ ] 18-01: Trigger Opus 4.6 review for freeze-signoff request package

### Phase 19: Manual Freeze Authority Handoff
**Goal:** Deliver a bounded, review-cleared package to the later manual freeze authority.
**Depends on:** Phase 18
**Requirements:** REQ-FREEZE-04
**Success Criteria** (what must be TRUE):
  1. A complete handoff bundle exists for manual freeze authority.
  2. AI automation clearly stops at the freeze authority boundary.
  3. The cockpit records that further action is manual-only.
**Plans:** TBD

Plans:
- [ ] 19-01: Package and hand off to manual freeze authority

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 12. GSD + Notion Cockpit Bootstrap | 1/1 | Complete | 2026-04-09 |
| 13. Checklist Completion Request Package | 0/1 | In progress | - |
| 14. Opus Review - Checklist Request | 0/1 | Not started | - |
| 15. Docs-Only Checklist Completion Action | 0/1 | Not started | - |
| 16. Opus Review - Checklist Action | 0/1 | Not started | - |
| 17. Final Freeze Signoff Request Package | 0/1 | Not started | - |
| 18. Opus Review - Freeze Signoff Request | 0/1 | Not started | - |
| 19. Manual Freeze Authority Handoff | 0/1 | Not started | - |
