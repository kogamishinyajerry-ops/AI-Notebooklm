# Post-Phase-7 Corrected Inventory Approval Planning Input

**Document ID:** APLH-PLANNING-INPUT-POST-P7-CORRECTED-INVENTORY-APPROVAL  
**Version:** 1.0.1  
**Date:** 2026-04-07  
**Status:** Historical Planning Input; Produced Corrected-Inventory Approval Planning Package  
**Target Session:** `APLH-PostPhase7-Corrected-Inventory-Approval-Planning`

---

## 1. Current Authoritative State

Historical result:

- This input produced [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLAN.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLAN.md).
- It also produced [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_INPUT.md).
- That review input produced [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_REPORT.md).
- Current status after review: `Corrected-Inventory Approval Planning Package Accepted`.
- Current next handoff: [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_REQUEST_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_REQUEST_INPUT.md).

- Phase 0 / 1 Accepted
- Phase 2A Accepted
- Phase 2B Accepted
- Phase 2C Accepted
- Phase 3-1 Accepted
- Phase 3-2 Accepted
- Phase 3-3 Accepted
- Phase 3-4 Accepted
- Phase 4 Planning Accepted
- Phase 4 Accepted
- Phase 5 Planning Accepted
- Phase 6 Accepted
- Phase 7 Accepted
- Post-Phase7 Formal Population Authorization Planning Accepted
- Post-Phase7 Authorization Request Package Accepted
- Executable Formal Population Approval Created
- Controlled Population Execution Blocked
- Controlled Population Blocker Resolution Requires Re-Approval

Authoritative blocker-resolution report:

- [`docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md)

Stale approval that must not be reused:

- [`artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml)

---

## 2. Planning Identity

The planner is:

- a corrected-inventory approval planner
- not an approval authority
- not a controlled population executor
- not a freeze approver
- not a Phase 8 executor

The planner may create a planning baseline and independent planning review input for approving the corrected `50`-file inventory.

This session must not create executable approval YAML, edit the old approval YAML in place, rerun `populate-formal`, manually copy formal artifacts, enter freeze-review intake, start Phase 8, or declare `freeze-complete`.

---

## 3. Must Read First

1. [`docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_INPUT.md)
2. [`docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_REPORT.md)
3. [`docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_BLOCKER_RESOLUTION_INPUT.md)
4. [`docs/POST_PHASE7_CONTROLLED_POPULATION_EXECUTION_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_EXECUTION_REPORT.md)
5. [`docs/POST_PHASE7_CONTROLLED_POPULATION_EXECUTION_INPUT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_CONTROLLED_POPULATION_EXECUTION_INPUT.md)
6. [`docs/POST_PHASE7_FORMAL_POPULATION_APPROVAL_ACTION_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_FORMAL_POPULATION_APPROVAL_ACTION_REPORT.md)
7. [`artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml)
8. [`docs/POST_PHASE7_FORMAL_POPULATION_APPROVAL_REQUEST.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_FORMAL_POPULATION_APPROVAL_REQUEST.md)
9. [`docs/POST_PHASE7_AUTHORIZATION_REQUEST_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/POST_PHASE7_AUTHORIZATION_REQUEST_REVIEW_REPORT.md)
10. [`docs/PHASE7_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_REVIEW_REPORT.md)
11. [`docs/PHASE7_IMPLEMENTATION_NOTES.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_IMPLEMENTATION_NOTES.md)
12. [`docs/PHASE7_FORMAL_POPULATION_PLAN.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE7_FORMAL_POPULATION_PLAN.md)
13. [`aero_prop_logic_harness/services/formal_population_executor.py`](/Users/Zhuanz/20260402 AI ControlLogicMaster/aero_prop_logic_harness/services/formal_population_executor.py)
14. [`aero_prop_logic_harness/models/promotion.py`](/Users/Zhuanz/20260402 AI ControlLogicMaster/aero_prop_logic_harness/models/promotion.py)
15. [`artifacts/examples/minimal_demo_set/abnormals/abn-0001.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/abnormals/abn-0001.yaml)
16. [`artifacts/examples/minimal_demo_set/modes/mode-0002.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/modes/mode-0002.yaml)
17. [`artifacts/examples/minimal_demo_set/trace/trace-0030.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/examples/minimal_demo_set/trace/trace-0030.yaml)
18. [`artifacts/.aplh/freeze_gate_status.yaml`](/Users/Zhuanz/20260402 AI ControlLogicMaster/artifacts/.aplh/freeze_gate_status.yaml)
19. [`README.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/README.md)
20. [`docs/README.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/README.md)

If this input conflicts with repository reality, repository reality wins.

---

## 4. Repository Reality to Preserve

The planning baseline must start from this state:

- `ABN-0001` coverage blocker has been fixed in demo source.
- `trace-0030.yaml` was added as `ABN-0001 -> MODE-0002`, `link_type: triggers_mode`.
- `validate-artifacts` and `check-trace` pass on `artifacts/examples/minimal_demo_set`.
- non-mutating sandbox validation passes after the correction.
- live corrected inventory is `50`.
- old approval `FORMAL-POP-APPROVAL-20260407-001` has `expected_file_count: 49`.
- old approval inventory validation fails with `49 != 50`.
- old approval must not be edited in place or reused for another controlled population attempt.
- checked-in formal artifact truth remains empty.
- `formal_population_audit_log.yaml` and `formal_promotions_log.yaml` do not exist.
- demo `.aplh/promotion_manifests/` still contains only the old blocked manifest.
- `artifacts/.aplh/freeze_gate_status.yaml` remains unchanged and manual-only.
- `freeze-complete`, `accepted_for_review`, and `pending_manual_decision` remain unset.

---

## 5. Planning Task

Create a corrected-inventory approval planning package that defines how to replace or supersede the stale `49`-file approval with a new independently reviewed approval path for the corrected `50`-file inventory.

Recommended planning baseline path:

- `docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLAN.md`

Recommended independent planning review input:

- `docs/POST_PHASE7_CORRECTED_INVENTORY_APPROVAL_PLANNING_REVIEW_INPUT.md`

The planning package must define:

- why re-approval is required
- why the old approval cannot be edited in place
- corrected inventory count and directory counts
- corrected evidence refs, including the blocker-resolution report and `trace-0030.yaml`
- proposed new approval ID, recommended `FORMAL-POP-APPROVAL-20260407-002`
- whether the new approval should supersede the old approval and how that is documented
- whether to leave the old approval file in place as historical executable-but-stale governance state or whether to require a non-executable supersession record before any future execution
- required gates before creating any new executable approval YAML
- required independent review before any new approval action
- boundaries prohibiting real population during planning and planning review

---

## 6. Absolute Prohibitions

This planning session must not:

- create executable approval YAML
- edit `FORMAL-POP-APPROVAL-20260407-001.yaml` in place
- delete the old approval YAML
- run `populate-formal`
- manually copy artifacts into checked-in formal artifact truth
- modify `artifacts/.aplh/freeze_gate_status.yaml`
- declare `freeze-complete`
- set `accepted_for_review`
- set `pending_manual_decision`
- create `formal_population_audit_log.yaml`
- create `formal_promotions_log.yaml`
- create a promoted manifest
- enter freeze-review intake
- start Phase 8 implementation
- weaken validators or reopen accepted schema / trace / graph / evaluator / runtime boundaries
- expand APLH into production runtime, certification package, UI, dashboard, or platform

---

## 7. Suggested Verification

Use non-mutating checks only:

```bash
.venv/bin/python -m aero_prop_logic_harness validate-artifacts --dir artifacts/examples/minimal_demo_set
.venv/bin/python -m aero_prop_logic_harness check-trace --dir artifacts/examples/minimal_demo_set
.venv/bin/python - <<'PY'
from pathlib import Path
from collections import Counter
from aero_prop_logic_harness.services.formal_population_executor import FormalPopulationExecutor
executor = FormalPopulationExecutor(Path("artifacts/examples/minimal_demo_set"), Path("artifacts"))
approval = executor.load_approval(Path("artifacts/.aplh/formal_population_approvals/FORMAL-POP-APPROVAL-20260407-001.yaml"))
inventory = executor.build_inventory()
print(approval.expected_file_count)
print(len(inventory))
print(",".join(executor.ALLOWED_SOURCE_DIRS))
print(dict(sorted(Counter(item.source_dir for item in inventory).items())))
try:
    executor.validate_approval_matches_inventory(approval, inventory)
    print("old_approval_inventory_valid=true")
except Exception as exc:
    print(f"old_approval_inventory_valid=false: {exc}")
PY
shasum -a 256 artifacts/.aplh/freeze_gate_status.yaml
find artifacts -maxdepth 2 -type f \( -path 'artifacts/requirements/*.yaml' -o -path 'artifacts/functions/*.yaml' -o -path 'artifacts/interfaces/*.yaml' -o -path 'artifacts/abnormals/*.yaml' -o -path 'artifacts/glossary/*.yaml' -o -path 'artifacts/trace/*.yaml' -o -path 'artifacts/modes/*.yaml' -o -path 'artifacts/transitions/*.yaml' -o -path 'artifacts/guards/*.yaml' \)
find artifacts -name 'formal_population_audit_log.yaml' -o -name 'formal_promotions_log.yaml'
```

Do not run `populate-formal`.

---

## 8. Required Output

The final state should be one of:

- `Corrected-Inventory Approval Planning Package Implemented, Pending Independent Review`
- `Corrected-Inventory Approval Planning Revision Required`

The output must include:

- current state
- recommended corrected-inventory approval package name
- why this is the smallest correct next step
- files created or updated
- explicit out-of-scope boundaries
- verification commands and results
- next independent planning review session name, model, and why

---

## 9. Recommended Routing

- Session: `APLH-PostPhase7-Corrected-Inventory-Approval-Planning`
- Primary model: `GPT-5.4`
- GPT-5.4 fallback: `GLM-5-Turbo` -> `Gemini 3.1 Pro`

After this planning package is produced, the next gate must be independent planning review. Do not jump directly to creating a new approval YAML or rerunning controlled population.
