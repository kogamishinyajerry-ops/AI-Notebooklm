"""
Replay / readback layer (Phase 3-2).

Reads persisted decision traces and provides structured readback,
tick-by-tick replay, and deterministic re-execution comparison.

Per PHASE3_ARCHITECTURE_PLAN §6.2:
  - Replay = from a saved DecisionTrace, re-run the same scenario and
    compare outputs for deterministic consistency.
  - This module also provides trace persistence (save/load).

IMPORTANT: This is NOT a second engine.  Re-execution delegates to the
existing ScenarioEngine.  The replay layer only orchestrates comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import ruamel.yaml

from aero_prop_logic_harness.models.scenario import Scenario
from aero_prop_logic_harness.services.decision_tracer import DecisionTrace, TransitionRecord
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine


# ── Trace persistence ────────────────────────────────────────────────


def save_trace(
    trace: DecisionTrace,
    baseline_dir: Path,
) -> Path:
    """Persist a DecisionTrace to the baseline's .aplh/traces/ directory.

    File naming: run_{run_id}_{scenario_id}_{timestamp}.yaml

    Returns the path to the written file.
    """
    traces_dir = baseline_dir / ".aplh" / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_part = (trace.run_id or "UNKNOWN").replace(" ", "_")
    scenario_part = (trace.scenario_id or "UNKNOWN").replace(" ", "_")
    filename = f"run_{run_part}_{scenario_part}_{ts}.yaml"

    data = trace.to_machine_readable()

    yaml = ruamel.yaml.YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)

    filepath = traces_dir / filename
    with open(filepath, "w") as f:
        yaml.dump(data, f)

    return filepath


def load_trace(filepath: Path) -> DecisionTrace:
    """Load a DecisionTrace from a persisted YAML file.

    Returns a DecisionTrace with all records restored.
    """
    yaml = ruamel.yaml.YAML(typ="safe")
    with open(filepath) as f:
        data = yaml.load(f)

    trace = DecisionTrace(
        run_id=data.get("run_id"),
        scenario_id=data.get("scenario_id"),
        evaluator_mode=data.get("evaluator_mode"),
    )
    for rec_data in data.get("records", []):
        record = TransitionRecord(**rec_data)
        trace.add_record(record)

    return trace


def list_traces(baseline_dir: Path) -> List[Path]:
    """List all trace files under .aplh/traces/ for a baseline."""
    traces_dir = baseline_dir / ".aplh" / "traces"
    if not traces_dir.is_dir():
        return []
    return sorted(traces_dir.glob("run_*.yaml"))


def find_trace_by_run_id(baseline_dir: Path, run_id: str) -> Optional[Path]:
    """Find a trace file by run_id.  Returns the first match or None."""
    for p in list_traces(baseline_dir):
        if run_id in p.name:
            return p
    # Fallback: read each file's run_id field
    for p in list_traces(baseline_dir):
        try:
            trace = load_trace(p)
            if trace.run_id == run_id:
                return p
        except Exception:
            continue
    return None


# ── Replay result ────────────────────────────────────────────────────


@dataclass
class ReplayResult:
    """Result of a deterministic replay comparison."""
    match: bool
    divergence_tick: Optional[int] = None
    divergence_detail: str = ""
    expected_trace: Optional[DecisionTrace] = None
    actual_trace: Optional[DecisionTrace] = None


# ── Replay reader ────────────────────────────────────────────────────


class ReplayReader:
    """Provides tick-by-tick readback and deterministic replay comparison.

    Per Phase 3-2 scope: replay is 'read existing trace', NOT a new
    execution engine.  For deterministic comparison, it delegates
    re-execution to the existing ScenarioEngine.
    """

    @staticmethod
    def readback(trace: DecisionTrace) -> List[Dict[str, Any]]:
        """Return a tick-by-tick readback of a decision trace.

        Each element contains:
          tick_id, mode_before, mode_after, candidates, transition_selected,
          actions_emitted, block_reason, run_id, scenario_id
        """
        result = []
        for rec in trace.records:
            result.append({
                "tick_id": rec.tick_id,
                "mode_before": rec.mode_before,
                "mode_after": rec.mode_after,
                "candidates_considered": rec.candidates_considered,
                "transition_selected": rec.transition_selected,
                "actions_emitted": rec.actions_emitted,
                "block_reason": rec.block_reason,
                "applied_signals": rec.applied_signals,
                "run_id": rec.run_id,
                "scenario_id": rec.scenario_id,
            })
        return result

    @staticmethod
    def replay_and_compare(
        scenario: Scenario,
        graph: ModeGraph,
        expected_trace: DecisionTrace,
        evaluator=None,
    ) -> ReplayResult:
        """Re-execute a scenario and compare with an expected trace.

        Delegates actual execution to ScenarioEngine.  Compares
        tick-by-tick: mode_before, mode_after, transition_selected,
        block_reason.

        Args:
            evaluator: Optional RicherEvaluator instance (Phase 3-3).
        """
        engine = ScenarioEngine(graph, evaluator=evaluator)
        actual_trace = engine.run_scenario(scenario)

        # Compare record by record
        expected_records = expected_trace.records
        actual_records = actual_trace.records

        min_len = min(len(expected_records), len(actual_records))

        for i in range(min_len):
            exp = expected_records[i]
            act = actual_records[i]

            if exp.tick_id != act.tick_id:
                return ReplayResult(
                    match=False,
                    divergence_tick=act.tick_id,
                    divergence_detail=(
                        f"Tick ID mismatch at index {i}: "
                        f"expected {exp.tick_id}, got {act.tick_id}"
                    ),
                    expected_trace=expected_trace,
                    actual_trace=actual_trace,
                )

            if exp.mode_before != act.mode_before:
                return ReplayResult(
                    match=False,
                    divergence_tick=exp.tick_id,
                    divergence_detail=(
                        f"mode_before mismatch: "
                        f"expected {exp.mode_before}, got {act.mode_before}"
                    ),
                    expected_trace=expected_trace,
                    actual_trace=actual_trace,
                )

            if exp.mode_after != act.mode_after:
                return ReplayResult(
                    match=False,
                    divergence_tick=exp.tick_id,
                    divergence_detail=(
                        f"mode_after mismatch: "
                        f"expected {exp.mode_after}, got {act.mode_after}"
                    ),
                    expected_trace=expected_trace,
                    actual_trace=actual_trace,
                )

            if exp.transition_selected != act.transition_selected:
                return ReplayResult(
                    match=False,
                    divergence_tick=exp.tick_id,
                    divergence_detail=(
                        f"transition_selected mismatch: "
                        f"expected {exp.transition_selected}, "
                        f"got {act.transition_selected}"
                    ),
                    expected_trace=expected_trace,
                    actual_trace=actual_trace,
                )

            # Compare block_reason (presence, not exact text)
            if bool(exp.block_reason) != bool(act.block_reason):
                return ReplayResult(
                    match=False,
                    divergence_tick=exp.tick_id,
                    divergence_detail=(
                        f"block_reason mismatch: "
                        f"expected {'present' if exp.block_reason else 'absent'}, "
                        f"got {'present' if act.block_reason else 'absent'}"
                    ),
                    expected_trace=expected_trace,
                    actual_trace=actual_trace,
                )

        # Check length mismatch
        if len(expected_records) != len(actual_records):
            return ReplayResult(
                match=False,
                divergence_tick=None,
                divergence_detail=(
                    f"Record count mismatch: "
                    f"expected {len(expected_records)}, got {len(actual_records)}"
                ),
                expected_trace=expected_trace,
                actual_trace=actual_trace,
            )

        return ReplayResult(
            match=True,
            expected_trace=expected_trace,
            actual_trace=actual_trace,
        )
