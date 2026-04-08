# APLH Scenario File Format

**Version:** 1.0.0 (Phase 3-2)

---

## Overview

Scenario files drive demo-scale execution of mode transition logic against a ModeGraph. Each scenario defines an initial mode, a sequence of signal update ticks, and optional regression expectations.

## File Location

Scenarios live under `{baseline}/scenarios/` with `.yml` extension:

```
artifacts/examples/minimal_demo_set/scenarios/
├── test.yml
├── normal_operation.yml
├── degraded_entry.yml
└── emergency_shutdown.yml
```

## Schema

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `scenario_id` | string | Yes | — | Unique identifier (e.g., `SCENARIO-DEMO`) |
| `title` | string | Yes | — | Human-readable title |
| `description` | string | No | null | Detailed description |
| `baseline_scope` | string | Yes | `"demo-scale"` | Must be `"demo-scale"` |
| `initial_mode_id` | string | Yes | — | Starting MODE ID (must exist in ModeGraph) |
| `ticks` | list | Yes | — | Ordered tick stream (see below) |
| `tags` | list[string] | No | `[]` | Classification tags |
| `version` | string | No | null | Scenario version string |
| `expected_final_mode` | string | No | null | Predicted end-state MODE ID |
| `expected_transitions` | list[string] | No | null | Predicted transition IDs |

### Tick Schema

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `tick_id` | int | Yes | — | Sequential integer (must be strictly increasing) |
| `signal_updates` | dict | Yes | `{}` | Signal reference → value map |
| `notes` | string | No | null | Description of this tick's intent |

### Signal Reference Format

Signal update keys must match the pattern `IFACE-NNNN.signal_name` (e.g., `IFACE-0001.oil_pressure`).

## Validation

Run `validate-scenario` before execution:

```bash
python -m aero_prop_logic_harness validate-scenario \
    --dir artifacts/examples/minimal_demo_set \
    --scenario artifacts/examples/minimal_demo_set/scenarios/test.yml
```

Checks performed (SV-1 through SV-6):

| Check | Description | Severity |
|-------|-------------|----------|
| SV-1 | `initial_mode_id` exists in ModeGraph | Error |
| SV-2 | Signal keys match `IFACE-NNNN.signal_name` | Error |
| SV-3 | `tick_id` values strictly increasing | Error |
| SV-4 | `baseline_scope` is `"demo-scale"` | Error |
| SV-5 | No empty ticks (no signals AND no notes) | Warning |
| SV-6 | `expected_final_mode` exists in ModeGraph | Error |

## Template

Copy `templates/scenario.template.yml` as a starting point for new scenarios.
