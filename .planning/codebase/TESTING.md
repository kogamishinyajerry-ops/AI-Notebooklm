# Testing

## Primary Commands

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m aero_prop_logic_harness validate-artifacts --dir artifacts`
- `.venv/bin/python -m aero_prop_logic_harness check-trace --dir artifacts`
- `.venv/bin/python -m aero_prop_logic_harness freeze-readiness --dir artifacts`

## Current Status (2026-04-09)

- `validate-artifacts --dir artifacts` -> pass
- `check-trace --dir artifacts` -> pass
- `freeze-readiness --dir artifacts` -> fail only at `Checklist Completed: Fail (Docs incomplete)`
- `pytest` -> `311 passed / 7 failed`

## Current Failing Test Clusters

1. `tests/test_control_surface.py::test_baseline_pollution`
2. `tests/test_example_artifacts.py::test_examples_baseline_isolation`
   - Both still expect `freeze-readiness --dir artifacts` to fail due to an empty graph, but the repo now has a populated formal graph and fails on docs incomplete instead.

3. `tests/test_phase4.py::test_formal_no_promotion_manifests`
4. `tests/test_phase4.py::test_formal_no_manifest_write_after_cli`
   - Formal `.aplh/promotion_manifests/` residue violates the older test expectation.

5. `tests/test_phase7.py::test_phase7_inventory_allowlist_excludes_scenarios_and_runtime_traces`
6. `tests/test_phase7.py::test_phase7_sandbox_validation_blocks_invalid_source_set`
7. `tests/test_phase7.py::test_phase7_controlled_population_writes_audits_and_reassesses`
   - These still expect a 50-file inventory and older sandbox behavior, while the current repo yields 51 populated files.

## Interpretation

The repo is operational for current governance work, but the test suite is not fully aligned with present artifact/state reality. The cockpit should expose this as a blocker before claiming fully healthy automated execution.
