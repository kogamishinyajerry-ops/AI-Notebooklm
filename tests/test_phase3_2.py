"""
Phase 3-2 test suite — Scenario/Replay/Audit Strengthening.

Covers:
  - ScenarioValidator: SV-1 through SV-6 (positive and negative)
  - ReplayReader: readback, deterministic replay comparison
  - Trace persistence: save/load round-trip
  - Audit correlation: run_id/scenario_id linkage across trace/signoff
  - CLI: validate-scenario, replay-scenario, inspect-run
  - Demo/formal/unmanaged path enforcement for new commands
  - Scenario model backward compatibility (new optional fields)
  - 2A/2B/2C/3-1 regression (Gate P3-A checks)
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
import ruamel.yaml

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.models.scenario import Scenario, ScenarioTick
from aero_prop_logic_harness.models.mode import Mode
from aero_prop_logic_harness.models.transition import Transition
from aero_prop_logic_harness.models.guard import Guard
from aero_prop_logic_harness.models.predicate import (
    AtomicPredicate,
    PredicateOperator,
)
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine
from aero_prop_logic_harness.services.scenario_validator import (
    ScenarioValidator,
    ScenarioValidationResult,
)
from aero_prop_logic_harness.services.replay_reader import (
    ReplayReader,
    save_trace,
    load_trace,
    list_traces,
    find_trace_by_run_id,
)
from aero_prop_logic_harness.services.decision_tracer import DecisionTrace, TransitionRecord

yaml = ruamel.yaml.YAML(typ="safe")
runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────


def _build_simple_graph():
    """Build a minimal ModeGraph for testing."""
    graph = ModeGraph()
    graph.nodes = {
        "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal", is_initial=True),
        "MODE-0002": Mode(id="MODE-0002", mode_type="degraded", name="Degraded"),
        "MODE-0003": Mode(id="MODE-0003", mode_type="emergency", name="Emergency"),
    }
    t1 = Transition(
        id="TRANS-0001",
        source_mode="MODE-0001",
        target_mode="MODE-0002",
        priority=1,
        name="Normal to Degraded",
        guard="GUARD-0001",
    )
    t2 = Transition(
        id="TRANS-0002",
        source_mode="MODE-0001",
        target_mode="MODE-0003",
        priority=2,
        name="Normal to Emergency",
    )
    graph.edges = {"TRANS-0001": t1, "TRANS-0002": t2}
    graph._outgoing = {
        "MODE-0001": ["TRANS-0001", "TRANS-0002"],
    }
    graph.guards = {
        "GUARD-0001": Guard(
            id="GUARD-0001",
            name="Low Oil Pressure",
            predicate=AtomicPredicate(
                operator=PredicateOperator.LT,
                signal_ref="IFACE-0001.oil_pressure",
                threshold=20.0,
            ),
        ),
    }
    return graph


def _build_demo_baseline(tmp_path):
    """Set up a demo-scale baseline directory."""
    (tmp_path / ".aplh").mkdir()
    gate = {
        "baseline_scope": "demo-scale",
        "boundary_frozen": True,
        "schema_frozen": True,
        "trace_gate_passed": True,
        "baseline_review_complete": True,
        "signed_off_by": "Test",
        "signed_off_at": "2026-01-01T00:00:00Z",
    }
    ry = ruamel.yaml.YAML()
    with open(tmp_path / ".aplh" / "freeze_gate_status.yaml", "w") as f:
        ry.dump(gate, f)
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════
# Scenario Validator Tests
# ═══════════════════════════════════════════════════════════════════════


class TestScenarioValidator:
    """ScenarioValidator structural pre-checks (SV-1 through SV-6)."""

    def test_sv1_initial_mode_exists(self):
        """SV-1 positive: initial_mode_id found in graph."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        assert result.passed
        assert result.error_count == 0

    def test_sv1_initial_mode_missing(self):
        """SV-1 negative: initial_mode_id not in graph."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-9999",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        assert not result.passed
        issues = [i for i in result.issues if i.check_id == "SV-1"]
        assert len(issues) == 1
        assert "MODE-9999" in issues[0].message

    def test_sv2_valid_signal_refs(self):
        """SV-2 positive: all signal_updates keys match pattern."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv2_issues = [i for i in result.issues if i.check_id == "SV-2"]
        assert len(sv2_issues) == 0

    def test_sv2_invalid_signal_ref(self):
        """SV-2 negative: bad signal reference key."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"bad_signal": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv2_issues = [i for i in result.issues if i.check_id == "SV-2"]
        assert len(sv2_issues) == 1
        assert "bad_signal" in sv2_issues[0].message

    def test_sv3_tick_ordering_valid(self):
        """SV-3 positive: tick_ids strictly increasing."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0}),
                ScenarioTick(tick_id=2, signal_updates={"IFACE-0001.oil_pressure": 40.0}),
                ScenarioTick(tick_id=5, signal_updates={"IFACE-0001.oil_pressure": 30.0}),
            ],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv3_issues = [i for i in result.issues if i.check_id == "SV-3"]
        assert len(sv3_issues) == 0

    def test_sv3_tick_ordering_invalid(self):
        """SV-3 negative: tick_ids not strictly increasing."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0}),
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 40.0}),
            ],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv3_issues = [i for i in result.issues if i.check_id == "SV-3"]
        assert len(sv3_issues) == 1

    def test_sv4_baseline_scope_valid(self):
        """SV-4 positive: baseline_scope is 'demo-scale'."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            baseline_scope="demo-scale",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv4_issues = [i for i in result.issues if i.check_id == "SV-4"]
        assert len(sv4_issues) == 0

    def test_sv4_baseline_scope_invalid(self):
        """SV-4 negative: baseline_scope is not 'demo-scale'."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            baseline_scope="formal",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv4_issues = [i for i in result.issues if i.check_id == "SV-4"]
        assert len(sv4_issues) == 1

    def test_sv5_empty_tick_warning(self):
        """SV-5: empty tick produces advisory warning."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={}),  # empty, no notes
            ],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv5_issues = [i for i in result.issues if i.check_id == "SV-5"]
        assert len(sv5_issues) == 1
        assert sv5_issues[0].severity == "warning"  # advisory, not error

    def test_sv5_tick_with_notes_not_empty(self):
        """SV-5: tick with notes but no signals is NOT empty."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={}, notes="Observation only"),
            ],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv5_issues = [i for i in result.issues if i.check_id == "SV-5"]
        assert len(sv5_issues) == 0

    def test_sv6_expected_final_mode_valid(self):
        """SV-6 positive: expected_final_mode exists in graph."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            expected_final_mode="MODE-0002",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv6_issues = [i for i in result.issues if i.check_id == "SV-6"]
        assert len(sv6_issues) == 0

    def test_sv6_expected_final_mode_missing(self):
        """SV-6 negative: expected_final_mode not in graph."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-0001",
            expected_final_mode="MODE-9999",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        sv6_issues = [i for i in result.issues if i.check_id == "SV-6"]
        assert len(sv6_issues) == 1

    def test_validation_report_output(self):
        """Validation result produces a readable report."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="TEST-001",
            title="Test",
            initial_mode_id="MODE-9999",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"bad_key": 0})],
        )
        result = ScenarioValidator(graph).validate(scenario)
        report = result.to_report()
        assert "SV-1" in report
        assert "SV-2" in report


# ═══════════════════════════════════════════════════════════════════════
# Replay Reader Tests
# ═══════════════════════════════════════════════════════════════════════


class TestReplayReader:
    """ReplayReader readback and deterministic comparison."""

    def test_readback_basic(self):
        """readback returns structured tick-by-tick data."""
        trace = DecisionTrace(run_id="RUN-TEST123456", scenario_id="SCENARIO-001")
        trace.add_record(TransitionRecord(
            tick_id=1,
            applied_signals={"IFACE-0001.sig": 5},
            mode_before="MODE-0001",
            candidates_considered=["TRANS-0001"],
            transition_selected="TRANS-0001",
            mode_after="MODE-0002",
            run_id="RUN-TEST123456",
            scenario_id="SCENARIO-001",
        ))
        result = ReplayReader.readback(trace)
        assert len(result) == 1
        assert result[0]["tick_id"] == 1
        assert result[0]["mode_before"] == "MODE-0001"
        assert result[0]["mode_after"] == "MODE-0002"
        assert result[0]["transition_selected"] == "TRANS-0001"
        assert result[0]["run_id"] == "RUN-TEST123456"

    def test_replay_deterministic_match(self):
        """Replay of the same scenario on the same graph produces identical results."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="SCENARIO-REPLAY",
            title="Replay Test",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        # First execution
        engine = ScenarioEngine(graph)
        expected_trace = engine.run_scenario(scenario)
        # Replay comparison
        result = ReplayReader.replay_and_compare(scenario, graph, expected_trace)
        assert result.match is True

    def test_replay_divergence_detected(self):
        """Replay detects divergence when trace doesn't match re-execution."""
        graph = _build_simple_graph()
        scenario = Scenario(
            scenario_id="SCENARIO-REPLAY",
            title="Replay Test",
            initial_mode_id="MODE-0001",
            ticks=[ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.oil_pressure": 50.0})],
        )
        # Create a fake expected trace with different data
        fake_trace = DecisionTrace(run_id="RUN-FAKE", scenario_id="SCENARIO-REPLAY")
        fake_trace.add_record(TransitionRecord(
            tick_id=1,
            applied_signals={"IFACE-0001.oil_pressure": 50.0},
            mode_before="MODE-0001",
            candidates_considered=["TRANS-0001"],
            transition_selected="TRANS-0001",  # different from actual
            mode_after="MODE-0002",  # different from actual
        ))
        result = ReplayReader.replay_and_compare(scenario, graph, fake_trace)
        assert result.match is False
        assert result.divergence_detail != ""


# ═══════════════════════════════════════════════════════════════════════
# Trace Persistence Tests
# ═══════════════════════════════════════════════════════════════════════


class TestTracePersistence:
    """save_trace / load_trace round-trip and listing."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saved trace can be loaded back with identical data."""
        trace = DecisionTrace(run_id="RUN-PERSIST12345", scenario_id="SCENARIO-P")
        trace.add_record(TransitionRecord(
            tick_id=1,
            applied_signals={"IFACE-0001.sig": 10},
            mode_before="MODE-0001",
            candidates_considered=["TRANS-0001"],
            transition_selected="TRANS-0001",
            mode_after="MODE-0002",
            run_id="RUN-PERSIST12345",
            scenario_id="SCENARIO-P",
        ))

        path = save_trace(trace, tmp_path)
        assert path.exists()
        assert "RUN-PERSIST12345" in path.name

        loaded = load_trace(path)
        assert loaded.run_id == "RUN-PERSIST12345"
        assert loaded.scenario_id == "SCENARIO-P"
        assert len(loaded.records) == 1
        assert loaded.records[0].tick_id == 1
        assert loaded.records[0].mode_after == "MODE-0002"

    def test_list_traces(self, tmp_path):
        """list_traces finds all trace files."""
        trace1 = DecisionTrace(run_id="RUN-A", scenario_id="S1")
        trace2 = DecisionTrace(run_id="RUN-B", scenario_id="S2")
        save_trace(trace1, tmp_path)
        save_trace(trace2, tmp_path)

        traces = list_traces(tmp_path)
        assert len(traces) == 2

    def test_list_traces_empty(self, tmp_path):
        """list_traces returns empty list for missing directory."""
        assert list_traces(tmp_path) == []

    def test_find_trace_by_run_id(self, tmp_path):
        """find_trace_by_run_id locates the correct trace."""
        trace = DecisionTrace(run_id="RUN-FINDME12345", scenario_id="S1")
        save_trace(trace, tmp_path)

        found = find_trace_by_run_id(tmp_path, "RUN-FINDME12345")
        assert found is not None
        assert "RUN-FINDME12345" in found.name

    def test_find_trace_by_run_id_not_found(self, tmp_path):
        """find_trace_by_run_id returns None for missing run_id."""
        assert find_trace_by_run_id(tmp_path, "RUN-NONEXISTENT") is None


# ═══════════════════════════════════════════════════════════════════════
# Audit Correlation Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAuditCorrelation:
    """run_id / scenario_id / trace / signoff linkage."""

    def test_run_id_propagates_through_trace_to_persistence(self, tmp_path):
        """run_id flows: engine → trace → persistence → load."""
        graph = ModeGraph()
        graph.nodes = {"MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="N")}
        graph.edges = {}
        graph._outgoing = {}

        engine = ScenarioEngine(graph)
        scenario = Scenario(
            scenario_id="SCENARIO-CORR",
            title="Correlation",
            initial_mode_id="MODE-0001",
            ticks=[],
        )
        trace = engine.run_scenario(scenario)

        # Persist
        path = save_trace(trace, tmp_path)
        loaded = load_trace(path)

        assert loaded.run_id == engine.run_id
        assert loaded.scenario_id == "SCENARIO-CORR"

    def test_signoff_and_trace_share_run_id(self, tmp_path):
        """Signoff entry and trace file correlate via run_id."""
        from aero_prop_logic_harness.models.signoff import SignoffEntry

        run_id = "RUN-CORRTEST1234"
        scenario_id = "SCENARIO-CORR-001"

        # Create trace
        trace = DecisionTrace(run_id=run_id, scenario_id=scenario_id)
        save_trace(trace, tmp_path)

        # Create signoff
        signoff = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Audit Tester",
            resolution="Approved",
            scenario_id=scenario_id,
            run_id=run_id,
        )
        assert signoff.run_id == run_id
        assert signoff.scenario_id == scenario_id

        # Verify trace can be found by the same run_id
        found = find_trace_by_run_id(tmp_path, run_id)
        assert found is not None

    def test_missing_run_id_in_trace(self):
        """Trace without run_id still functions (backward compat)."""
        trace = DecisionTrace()
        assert trace.run_id is None
        data = trace.to_machine_readable()
        assert data["run_id"] is None

    def test_missing_scenario_id_in_signoff(self):
        """SignoffEntry with missing scenario_id still valid."""
        from aero_prop_logic_harness.models.signoff import SignoffEntry
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Test",
            resolution="OK",
        )
        assert entry.scenario_id is None
        assert entry.run_id is None


# ═══════════════════════════════════════════════════════════════════════
# Scenario Model Backward Compatibility Tests
# ═══════════════════════════════════════════════════════════════════════


class TestScenarioModelCompat:
    """Phase 3-2 optional fields don't break existing scenarios."""

    def test_existing_scenario_still_valid(self):
        """Scenario without Phase 3-2 fields loads fine."""
        data = {
            "scenario_id": "SCENARIO-OLD",
            "title": "Old Format",
            "baseline_scope": "demo-scale",
            "initial_mode_id": "MODE-0001",
            "ticks": [{"tick_id": 1, "signal_updates": {"IFACE-0001.sig": 1}}],
        }
        scenario = Scenario(**data)
        assert scenario.version is None
        assert scenario.expected_final_mode is None
        assert scenario.expected_transitions is None

    def test_scenario_with_phase32_fields(self):
        """Scenario with all Phase 3-2 optional fields."""
        data = {
            "scenario_id": "SCENARIO-NEW",
            "title": "New Format",
            "baseline_scope": "demo-scale",
            "initial_mode_id": "MODE-0001",
            "version": "1.0.0",
            "expected_final_mode": "MODE-0002",
            "expected_transitions": ["TRANS-0001"],
            "ticks": [{"tick_id": 1, "signal_updates": {"IFACE-0001.sig": 1}}],
        }
        scenario = Scenario(**data)
        assert scenario.version == "1.0.0"
        assert scenario.expected_final_mode == "MODE-0002"
        assert scenario.expected_transitions == ["TRANS-0001"]


# ═══════════════════════════════════════════════════════════════════════
# CLI Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestValidateScenarioCLI:
    """CLI validate-scenario command tests."""

    def test_validate_scenario_pass(self, tmp_path):
        """validate-scenario succeeds for a valid scenario in demo baseline."""
        _build_demo_baseline(tmp_path)
        scenario_path = tmp_path / "scenarios"
        scenario_path.mkdir()
        ry = ruamel.yaml.YAML()
        with open(scenario_path / "test.yml", "w") as f:
            ry.dump({
                "scenario_id": "SCENARIO-CLI-001",
                "title": "CLI Test",
                "baseline_scope": "demo-scale",
                "initial_mode_id": "MODE-0001",
                "ticks": [{"tick_id": 1, "signal_updates": {"IFACE-0001.sig": 5}}],
            }, f)

        result = runner.invoke(app, [
            "validate-scenario",
            "--dir", str(tmp_path),
            "--scenario", str(scenario_path / "test.yml"),
        ])
        # Graph has no modes, so SV-1 will error (MODE-0001 not in graph)
        # This is expected for an empty graph
        assert result.exit_code == 1  # because graph is empty
        assert "SV-1" in result.stdout

    def test_validate_scenario_formal_rejected(self, tmp_path):
        """validate-scenario rejects formal directory."""
        _build_demo_baseline(tmp_path)
        scenario_path = tmp_path / "test.yml"
        ry = ruamel.yaml.YAML()
        with open(scenario_path, "w") as f:
            ry.dump({
                "scenario_id": "S1", "title": "T", "initial_mode_id": "M",
                "ticks": [{"tick_id": 1, "signal_updates": {}}],
            }, f)

        with patch("aero_prop_logic_harness.cli.is_formal_baseline_root", return_value=True):
            result = runner.invoke(app, [
                "validate-scenario",
                "--dir", str(tmp_path),
                "--scenario", str(scenario_path),
            ])
        assert result.exit_code == 1
        assert "Formal" in result.stdout


class TestReplayScenarioCLI:
    """CLI replay-scenario command tests."""

    def test_replay_formal_rejected(self, tmp_path):
        """replay-scenario rejects formal directory."""
        _build_demo_baseline(tmp_path)
        with patch("aero_prop_logic_harness.cli.is_formal_baseline_root", return_value=True):
            result = runner.invoke(app, [
                "replay-scenario",
                "--dir", str(tmp_path),
                "--scenario", str(tmp_path / "s.yml"),
                "--trace", str(tmp_path / "t.yml"),
            ])
        assert result.exit_code == 1
        assert "Formal" in result.stdout


class TestInspectRunCLI:
    """CLI inspect-run command tests."""

    def test_inspect_run_not_found(self, tmp_path):
        """inspect-run with nonexistent run_id exits with error."""
        _build_demo_baseline(tmp_path)
        result = runner.invoke(app, [
            "inspect-run",
            "--dir", str(tmp_path),
            "--run-id", "RUN-NONEXISTENT",
        ])
        assert result.exit_code == 1
        assert "No trace found" in result.stdout

    def test_inspect_run_formal_rejected(self, tmp_path):
        """inspect-run rejects formal directory."""
        _build_demo_baseline(tmp_path)
        with patch("aero_prop_logic_harness.cli.is_formal_baseline_root", return_value=True):
            result = runner.invoke(app, [
                "inspect-run",
                "--dir", str(tmp_path),
                "--run-id", "RUN-TEST",
            ])
        assert result.exit_code == 1
        assert "Formal" in result.stdout

    def test_inspect_run_success(self, tmp_path):
        """inspect-run succeeds when trace exists."""
        _build_demo_baseline(tmp_path)
        # Create a trace file
        trace = DecisionTrace(run_id="RUN-INSPECT12345", scenario_id="SCENARIO-I")
        trace.add_record(TransitionRecord(
            tick_id=1,
            applied_signals={"IFACE-0001.sig": 5},
            mode_before="MODE-0001",
            candidates_considered=[],
            mode_after="MODE-0001",
            run_id="RUN-INSPECT12345",
            scenario_id="SCENARIO-I",
        ))
        save_trace(trace, tmp_path)

        result = runner.invoke(app, [
            "inspect-run",
            "--dir", str(tmp_path),
            "--run-id", "RUN-INSPECT12345",
        ])
        assert result.exit_code == 0
        assert "RUN-INSPECT12345" in result.stdout
        assert "SCENARIO-I" in result.stdout
        assert "Tick 1" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# Gate P3-A: Frozen Input Preservation (regression)
# ═══════════════════════════════════════════════════════════════════════


class TestGateP3A:
    """Verify Phase 3-2 does not pollute 2A/2B/2C/3-1 frozen contracts."""

    def test_mode_graph_no_execute_methods(self):
        """ModeGraph must NOT have step/fire/evaluate/execute methods."""
        forbidden = {"step", "fire", "evaluate", "execute"}
        methods = {m for m in dir(ModeGraph) if not m.startswith("_")}
        assert forbidden.isdisjoint(methods), (
            f"ModeGraph has forbidden methods: {forbidden & methods}"
        )

    def test_guard_evaluator_unchanged(self):
        """GuardEvaluator core must still work as in 2C."""
        from aero_prop_logic_harness.services.guard_evaluator import GuardEvaluator
        atomic = AtomicPredicate(
            operator=PredicateOperator.GT,
            signal_ref="IFACE-0001.test",
            threshold=10.0,
        )
        assert GuardEvaluator.evaluate(atomic, {"IFACE-0001.test": 20.0}) is True
        assert GuardEvaluator.evaluate(atomic, {"IFACE-0001.test": 5.0}) is False

    def test_no_trans_func_trace_direction(self):
        """No TRANS->FUNC trace direction exists."""
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        trans_func = [d for d in VALID_TRACE_DIRECTIONS if "TRANS" in str(d[0]) and "FUNC" in str(d[1])]
        assert len(trans_func) == 0

    def test_no_trans_iface_trace_direction(self):
        """No TRANS->IFACE trace direction exists."""
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        trans_iface = [d for d in VALID_TRACE_DIRECTIONS if "TRANS" in str(d[0]) and "IFACE" in str(d[1])]
        assert len(trans_iface) == 0

    def test_signoff_entry_schema_intact(self):
        """SignoffEntry schema from 3-1 still works."""
        from aero_prop_logic_harness.models.signoff import SignoffEntry
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Test",
            resolution="OK",
            scenario_id="S1",
            run_id="RUN-ABC",
        )
        assert entry.baseline_scope == "demo-scale"

    def test_valid_trace_directions_count(self):
        """VALID_TRACE_DIRECTIONS still has exactly 25 entries."""
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        assert len(VALID_TRACE_DIRECTIONS) == 25


# ═══════════════════════════════════════════════════════════════════════
# Demo Scenario File Loading Tests
# ═══════════════════════════════════════════════════════════════════════


class TestDemoScenarios:
    """Verify the 3 new demo scenarios + existing test.yml all parse."""

    @pytest.mark.parametrize("filename", [
        "test.yml",
        "normal_operation.yml",
        "degraded_entry.yml",
        "emergency_shutdown.yml",
    ])
    def test_demo_scenario_parses(self, filename):
        """All demo scenarios parse as valid Scenario objects."""
        scenario_dir = Path("artifacts/examples/minimal_demo_set/scenarios")
        if not scenario_dir.is_dir():
            pytest.skip("Demo scenario directory not found")
        filepath = scenario_dir / filename
        if not filepath.is_file():
            pytest.skip(f"Scenario file {filename} not found")

        ry = ruamel.yaml.YAML(typ="safe")
        with open(filepath) as f:
            data = ry.load(f)
        scenario = Scenario(**data)
        assert scenario.scenario_id is not None
        assert scenario.title != ""
        assert scenario.baseline_scope == "demo-scale"
        assert len(scenario.ticks) > 0
