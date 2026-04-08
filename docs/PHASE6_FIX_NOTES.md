# APLH Phase 6 Revision Fix Notes

**Document ID:** APLH-FIX-P6-1  
**Version:** 1.0.1  
**Date:** 2026-04-07  
**Status:** Accepted

---

## 1. Fix Scope

This fix addresses the P1 finding from [`docs/PHASE6_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE6_REVIEW_REPORT.md):

- Manual review intake could override failed machine readiness and elevate `formal_state` to `accepted_for_review` even when the formal baseline was still `unpopulated`.

The fix is intentionally narrow. It does not modify `freeze_gate_status.yaml`, does not populate the formal baseline, and does not widen Phase 6 scope.

---

## 2. Code Changes

Updated [`aero_prop_logic_harness/services/freeze_review_preparer.py`](/Users/Zhuanz/20260402 AI ControlLogicMaster/aero_prop_logic_harness/services/freeze_review_preparer.py):

- `manual_state` now affects `formal_state` only when `review_preparation_state == "ready_for_freeze_review"`.
- `G6-E` now passes only when manual review intake is present and the machine-generated review preparation state has already reached `ready_for_freeze_review`.
- If a manual intake state exists before machine readiness, the report records a blocking condition explaining that the manual state is ignored until `ready_for_freeze_review`.

Updated [`tests/test_phase6.py`](/Users/Zhuanz/20260402 AI ControlLogicMaster/tests/test_phase6.py):

- Added a regression test proving that an unpopulated formal baseline with a manual `accepted_for_review` entry still reports:
  - `formal_state: unpopulated`
  - `population_state: unpopulated`
  - `validation_state: not_validated`
  - `review_preparation_state: not_ready`
  - `G6-E` not passed

---

## 3. Current Verification

Observed after the fix:

- `.venv/bin/python -m pytest tests/test_phase6.py -q` -> `5 passed`
- `.venv/bin/python -m pytest tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q` -> `27 passed`
- `.venv/bin/python -m pytest -q` -> `312 passed`
- `.venv/bin/python -m aero_prop_logic_harness assess-readiness --dir artifacts --demo artifacts/examples/minimal_demo_set` -> exit `1`, formal state `unpopulated`
- `.venv/bin/python -m aero_prop_logic_harness execute-promotion --help` -> exit `0`

The independent fix re-review accepted these results; see [`docs/PHASE6_FIX_REVIEW_REPORT.md`](/Users/Zhuanz/20260402 AI ControlLogicMaster/docs/PHASE6_FIX_REVIEW_REPORT.md).

For future regression checks, rerun:

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m pytest tests/test_phase4.py tests/test_phase5.py tests/test_phase6.py -q`
- `.venv/bin/python -m aero_prop_logic_harness assess-readiness --dir artifacts --demo artifacts/examples/minimal_demo_set`
- `.venv/bin/python -m aero_prop_logic_harness execute-promotion --help`

---

## 4. Status

The P1 fix was accepted by independent re-review.

Current state:

- `Phase 6 Accepted`
