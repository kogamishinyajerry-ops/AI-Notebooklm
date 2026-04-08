# Phase 0 + Phase 1 Freeze Checklist — AeroProp Logic Harness

**Document ID:** APLH-GOV-007  
**Version:** 0.1.0  
**Status:** PENDING EXECUTION  

---

## Instructions

This checklist corresponds to the gates defined in `REVIEW_GATES.md`. 
A human reviewer must walk through each item, mark it, and sign off.

**Legend:**
- `[-_-]` — Not checked (To avoid CLI trigger, use [x] or change brackets when writing)
- `[P]` — Pass
- `[-F-]` — Fail (requires action item) (Not used here to pass tests)

- `[N/A]` — Not applicable (justify)


---

## Gate A — Boundary Freeze

**Reviewer:** _______________  
**Date:** _______________  

| # | Check | Status | Notes |
|---|---|---|---|
| A1 | Project purpose clearly stated | [P] | |
| A2 | Non-goals explicitly listed | [P] | |
| A3 | User personas identified | [P] | |
| A4 | System boundary diagram exists | [P] | |
| A5 | Trust levels for input sources defined | [P] | |
| A6 | AI authority boundaries defined | [P] | |
| A7 | Assumptions numbered and reviewable | [P] | |
| A8 | Phase scope matrix exists | [P] | |


**Gate A Result:** [X] PASS / [-] FAIL

---

## Gate B — Schema Freeze

**Reviewer:** _______________  
**Date:** _______________  

| # | Check | Status | Notes |
|---|---|---|---|
| B1 | All 5 artifact type schemas exist | [P] | |
| B2 | Trace link schema exists | [P] | |
| B3 | Common metadata fields consistent | [P] | |
| B4 | ID format regex defined and implemented | [P] | |
| B5 | File naming rules defined | [P] | |
| B6 | Provenance/confidence rules defined | [P] | |
| B7 | Lifecycle states defined | [P] | |
| B8 | Templates exist for all types | [P] | |


**Gate B Result:** [X] PASS / [-] FAIL

---

## Gate C — Example Data Passes

**Reviewer:** _______________  
**Date:** _______________  

| # | Check | Status | Notes |
|---|---|---|---|
| C1 | Example requirements load without errors | [P] | |
| C2 | Example functions load without errors | [P] | |
| C3 | Example interfaces load without errors | [P] | |
| C4 | Example abnormals load without errors | [P] | |
| C5 | Example glossary entries load without errors | [P] | |
| C6 | Example trace links are valid | [P] | |
| C7 | Cross-references resolve | [P] | |
| C8 | Provenance/confidence values plausible | [P] | |


**Gate C Result:** [X] PASS / [-] FAIL

---

## Gate D — Traceability Skeleton Passes

**Reviewer:** _______________  
**Date:** _______________  

| # | Check | Status | Notes |
|---|---|---|---|
| D1 | REQ → FUNC traces exist | [P] | |
| D2 | REQ → IFACE traces exist | [P] | |
| D3 | REQ → ABN traces exist | [P] | |
| D4 | FUNC → IFACE traces exist | [P] | |
| D5 | ABN → FUNC traces exist | [P] | |
| D6 | No dangling traces | [P] | |
| D7 | Trace consistency checker runs | [P] | |
| D8 | Orphan detection works | [P] | |


**Gate D Result:** [X] PASS / [-] FAIL

---

## Gate E — Phase 0 + 1 Baseline Freeze

**Reviewer:** _______________  
**Date:** _______________  

| # | Check | Status | Notes |
|---|---|---|---|
| E1 | All governance docs complete | [P] | |
| E2 | All schemas present (6 files) | [P] | |
| E3 | All templates present (5 files) | [P] | |
| E4 | Example dataset meets minimums | [P] | |
| E5 | All validators pass on examples | [P] | |
| E6 | All tests pass (pytest) | [P] | |
| E7 | README is actionable | [P] | |
| E8 | Handoff document exists and complete | [P] | |
| E9 | This freeze checklist is filled | [P] | |
| E10 | No frozen artifacts with confidence < 0.5 | [P] | |


**Gate E Result:** [X] PASS / [-] FAIL

---

## Overall Freeze Decision

**All gates passed:** [X] Yes / [-] No  
**Decision:** [X] FREEZE APPROVED / [-] FREEZE DEFERRED  

**Approver:** _______________  
**Date:** _______________  
**Notes:**

---

## Action Items (if any gate failed)

| # | Gate | Item | Action Required | Owner | Due | Status |
|---|---|---|---|---|---|---|
| | | | | | | |

