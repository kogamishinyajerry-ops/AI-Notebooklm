"""
Phase 3 test suite — Signoff audit, run_id propagation, and tech debt closure.

Covers:
  - TD-1: test_signoff_formal_rejected with real assertions
  - TD-3: reviewer parameterization
  - TD-4: scenario_id / run_id correlation
  - SignoffEntry schema validation
  - DecisionTrace run_id / scenario_id propagation
  - ScenarioEngine run_id generation
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
import ruamel.yaml

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.models.signoff import SignoffEntry
from aero_prop_logic_harness.services.decision_tracer import DecisionTrace, TransitionRecord
from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine
from aero_prop_logic_harness.models.scenario import Scenario

yaml = ruamel.yaml.YAML(typ="safe")
runner = CliRunner()


# ── SignoffEntry Schema Tests ─────────────────────────────────────────


class TestSignoffEntrySchema:
    """Tests for the SignoffEntry Pydantic schema (Phase 3-1 hardened)."""

    # ── Positive tests ────────────────────────────────────────────────

    def test_signoff_entry_minimal(self):
        """Minimal valid signoff entry with ISO 8601 timestamp."""
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Alice Engineer",
            resolution="Priority conflict reviewed and accepted",
        )
        assert entry.reviewer == "Alice Engineer"
        assert entry.baseline_scope == "demo-scale"
        assert entry.scenario_id is None
        assert entry.run_id is None

    def test_signoff_entry_full(self):
        """Full signoff entry with scenario_id and run_id."""
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Bob Engineer",
            resolution="Degraded recovery approved",
            scenario_id="SCENARIO-DEMO",
            run_id="RUN-3A7F1BC9D2E4",
            baseline_scope="demo-scale",
        )
        assert entry.scenario_id == "SCENARIO-DEMO"
        assert entry.run_id == "RUN-3A7F1BC9D2E4"

    def test_signoff_entry_timestamp_with_fractional_seconds(self):
        """Fractional-second ISO 8601 timestamps are valid."""
        entry = SignoffEntry(
            timestamp="2026-04-04T09:40:52.640672Z",
            reviewer="Test",
            resolution="OK",
        )
        assert entry.timestamp == "2026-04-04T09:40:52.640672Z"

    def test_signoff_entry_timestamp_without_z(self):
        """ISO 8601 timestamp without trailing Z is valid."""
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00+08:00",
            reviewer="Test",
            resolution="OK",
        )
        assert entry.timestamp == "2026-04-04T12:00:00+08:00"

    def test_signoff_entry_serialization(self):
        """model_dump(exclude_none=True) produces clean YAML output."""
        entry = SignoffEntry(
            timestamp="2026-04-04T12:00:00Z",
            reviewer="Alice",
            resolution="Checked",
            scenario_id="SCENARIO-001",
        )
        dumped = entry.model_dump(exclude_none=True)
        assert "run_id" not in dumped  # None fields excluded
        assert dumped["scenario_id"] == "SCENARIO-001"
        assert dumped["baseline_scope"] == "demo-scale"

    # ── Negative tests: extra field ───────────────────────────────────

    def test_signoff_entry_extra_field_rejected(self):
        """extra='forbid' prevents uncontrolled schema drift."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SignoffEntry(
                timestamp="2026-04-04T12:00:00Z",
                reviewer="Test",
                resolution="test",
                unknown_field="oops",
            )

    # ── Negative tests: baseline_scope ────────────────────────────────

    def test_signoff_invalid_baseline_scope_freeze_complete(self):
        """baseline_scope='freeze-complete' MUST be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SignoffEntry(
                timestamp="2026-04-04T12:00:00Z",
                reviewer="Test",
                resolution="test",
                baseline_scope="freeze-complete",
            )

    def test_signoff_invalid_baseline_scope_formal(self):
        """baseline_scope='formal' MUST be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SignoffEntry(
                timestamp="2026-04-04T12:00:00Z",
                reviewer="Test",
                resolution="test",
                baseline_scope="formal",
            )

    def test_signoff_invalid_baseline_scope_empty(self):
        """baseline_scope='' (empty string) MUST be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SignoffEntry(
                timestamp="2026-04-04T12:00:00Z",
                reviewer="Test",
                resolution="test",
                baseline_scope="",
            )

    # ── Negative tests: timestamp ─────────────────────────────────────

    def test_signoff_invalid_timestamp_garbage(self):
        """timestamp='not-a-time' MUST be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="timestamp must be a full ISO 8601 datetime"):
            SignoffEntry(
                timestamp="not-a-time",
                reviewer="Test",
                resolution="test",
            )

    def test_signoff_invalid_timestamp_partial_date(self):
        """timestamp='2026-04-04' (date only, no time) MUST be rejected."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="timestamp must be a full ISO 8601 datetime"):
            SignoffEntry(
                timestamp="2026-04-04",
                reviewer="Test",
                resolution="test",
            )


# ── DecisionTrace Audit Correlation Tests ─────────────────────────────


class TestDecisionTraceAudit:
    """Tests for run_id/scenario_id propagation in DecisionTrace."""

    def test_trace_carries_run_id(self):
        trace = DecisionTrace(run_id="RUN-TEST123456", scenario_id="SCENARIO-001")
        assert trace.run_id == "RUN-TEST123456"
        assert trace.scenario_id == "SCENARIO-001"

    def test_trace_human_readable_includes_header(self):
        trace = DecisionTrace(run_id="RUN-TEST123456", scenario_id="SCENARIO-001")
        output = trace.to_human_readable()
        assert "Run ID:       RUN-TEST123456" in output
        assert "Scenario ID:  SCENARIO-001" in output

    def test_trace_human_readable_no_header_when_empty(self):
        trace = DecisionTrace()
        output = trace.to_human_readable()
        assert "Run ID:" not in output
        assert "Scenario ID:" not in output

    def test_trace_machine_readable(self):
        trace = DecisionTrace(run_id="RUN-ABC", scenario_id="SCENARIO-X")
        rec = TransitionRecord(
            tick_id=1,
            applied_signals={"IFACE-0001.sig": 5},
            mode_before="MODE-0001",
            candidates_considered=["TRANS-0001"],
            mode_after="MODE-0002",
            run_id="RUN-ABC",
            scenario_id="SCENARIO-X",
        )
        trace.add_record(rec)
        data = trace.to_machine_readable()
        assert data["run_id"] == "RUN-ABC"
        assert data["scenario_id"] == "SCENARIO-X"
        assert len(data["records"]) == 1
        assert data["records"][0]["run_id"] == "RUN-ABC"

    def test_transition_record_carries_audit_fields(self):
        rec = TransitionRecord(
            tick_id=1,
            applied_signals={},
            mode_before="MODE-0001",
            candidates_considered=[],
            mode_after="MODE-0001",
            run_id="RUN-XYZ",
            scenario_id="SCENARIO-T",
        )
        assert rec.run_id == "RUN-XYZ"
        assert rec.scenario_id == "SCENARIO-T"


# ── ScenarioEngine run_id Tests ───────────────────────────────────────


class TestScenarioEngineRunId:
    """Tests for run_id generation and propagation in ScenarioEngine."""

    def test_generate_run_id_format(self):
        run_id = ScenarioEngine.generate_run_id()
        assert run_id.startswith("RUN-")
        assert len(run_id) == 16  # "RUN-" + 12 hex chars

    def test_generate_run_id_uniqueness(self):
        ids = {ScenarioEngine.generate_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_engine_propagates_run_id(self):
        """Engine generates run_id and it appears in trace and records."""
        from aero_prop_logic_harness.services.mode_graph import ModeGraph
        from aero_prop_logic_harness.models.mode import Mode

        graph = ModeGraph()
        graph.nodes = {
            "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal"),
        }
        graph.edges = {}
        graph._outgoing = {}

        engine = ScenarioEngine(graph)
        scenario = Scenario(
            scenario_id="SCENARIO-TEST",
            title="Run ID Test",
            baseline_scope="demo-scale",
            initial_mode_id="MODE-0001",
            ticks=[],
        )
        trace = engine.run_scenario(scenario)
        assert engine.run_id is not None
        assert engine.run_id.startswith("RUN-")
        assert trace.run_id == engine.run_id
        assert trace.scenario_id == "SCENARIO-TEST"

    def test_engine_accepts_run_id_override(self):
        from aero_prop_logic_harness.services.mode_graph import ModeGraph
        from aero_prop_logic_harness.models.mode import Mode

        graph = ModeGraph()
        graph.nodes = {
            "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal"),
        }
        graph.edges = {}
        graph._outgoing = {}

        engine = ScenarioEngine(graph)
        scenario = Scenario(
            scenario_id="SCENARIO-TEST",
            title="Override Test",
            baseline_scope="demo-scale",
            initial_mode_id="MODE-0001",
            ticks=[],
        )
        trace = engine.run_scenario(scenario, run_id="RUN-OVERRIDE12345")
        assert engine.run_id == "RUN-OVERRIDE12345"
        assert trace.run_id == "RUN-OVERRIDE12345"

    def test_engine_records_carry_run_id(self):
        """Every TransitionRecord in a run carries the run_id and scenario_id."""
        from aero_prop_logic_harness.services.mode_graph import ModeGraph
        from aero_prop_logic_harness.models.mode import Mode
        from aero_prop_logic_harness.models.transition import Transition

        graph = ModeGraph()
        graph.nodes = {
            "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal", is_initial=True),
            "MODE-0002": Mode(id="MODE-0002", mode_type="normal", name="Other"),
        }
        t1 = Transition(id="TRANS-0001", source_mode="MODE-0001", target_mode="MODE-0002", priority=1, name="T1")
        graph.edges = {"TRANS-0001": t1}
        graph._outgoing = {"MODE-0001": ["TRANS-0001"]}

        engine = ScenarioEngine(graph)
        scenario = Scenario(
            scenario_id="SCENARIO-REC",
            title="Record Test",
            baseline_scope="demo-scale",
            initial_mode_id="MODE-0001",
            ticks=[{"tick_id": 1, "signal_updates": {}}],
        )
        trace = engine.run_scenario(scenario)
        assert len(trace.records) == 1
        assert trace.records[0].run_id == engine.run_id
        assert trace.records[0].scenario_id == "SCENARIO-REC"


# ── TD-1: Formal Signoff Rejection Tests ──────────────────────────────


class TestSignoffFormalRejected:
    """TD-1: Replace empty pass placeholder with real assertion.

    The formal signoff rejection is tested by monkeypatching
    is_formal_baseline_root to return True for our test directory.
    """

    def test_signoff_formal_rejected_via_monkeypatch(self, tmp_path):
        """Formal directory MUST reject signoff with exit code 1."""
        # Set up a directory that looks like a managed demo baseline
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

        # Monkeypatch is_formal_baseline_root to treat tmp_path as formal
        with patch(
            "aero_prop_logic_harness.cli.is_formal_baseline_root",
            return_value=True,
        ):
            result = runner.invoke(app, [
                "signoff-demo",
                "--dir", str(tmp_path),
                "--reviewer", "Test Reviewer",
                "--resolution", "Should be rejected",
            ])
        assert result.exit_code == 1
        assert "Cannot sign off in Formal baseline" in result.stdout

    def test_signoff_unmanaged_still_rejected(self, tmp_path):
        """Unmanaged baseline still rejected (regression from 2C)."""
        result = runner.invoke(app, [
            "signoff-demo",
            "--dir", str(tmp_path),
            "--reviewer", "Test",
            "--resolution", "test",
        ])
        assert result.exit_code == 1
        assert "Unmanaged Environment Error" in result.stdout


# ── TD-3: Reviewer Parameterization Tests ─────────────────────────────


class TestReviewerParameterization:
    """TD-3: Verify reviewer is parameterized, not hardcoded."""

    def test_signoff_writes_custom_reviewer(self, tmp_path):
        """signoff-demo writes the --reviewer value, not 'Demo Reviewer'."""
        # Set up demo-scale baseline
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

        result = runner.invoke(app, [
            "signoff-demo",
            "--dir", str(tmp_path),
            "--reviewer", "Jane Smith",
            "--resolution", "Approved after review",
            "--scenario-id", "SCENARIO-TEST",
            "--run-id", "RUN-ABC123DEF456",
        ])
        assert result.exit_code == 0

        # Read back signoffs
        ry_safe = ruamel.yaml.YAML(typ="safe")
        signoff_file = tmp_path / ".aplh" / "review_signoffs.yaml"
        with open(signoff_file) as f:
            data = ry_safe.load(f)

        assert isinstance(data, list)
        assert len(data) == 1
        entry = data[0]
        assert entry["reviewer"] == "Jane Smith"
        assert entry["resolution"] == "Approved after review"
        assert entry["scenario_id"] == "SCENARIO-TEST"
        assert entry["run_id"] == "RUN-ABC123DEF456"
        assert entry["baseline_scope"] == "demo-scale"

    def test_signoff_reviewer_required(self):
        """--reviewer is a required parameter (not optional)."""
        result = runner.invoke(app, [
            "signoff-demo",
            "--dir", "/tmp",
            "--resolution", "test",
        ])
        # Should fail because --reviewer is missing
        assert result.exit_code != 0

    def test_signoff_no_hardcoded_demo_reviewer(self, tmp_path):
        """Verify 'Demo Reviewer' never appears in output."""
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

        result = runner.invoke(app, [
            "signoff-demo",
            "--dir", str(tmp_path),
            "--reviewer", "Real Reviewer",
            "--resolution", "OK",
        ])
        assert result.exit_code == 0

        ry_safe = ruamel.yaml.YAML(typ="safe")
        signoff_file = tmp_path / ".aplh" / "review_signoffs.yaml"
        with open(signoff_file) as f:
            data = ry_safe.load(f)
        assert data[0]["reviewer"] == "Real Reviewer"
        assert data[0]["reviewer"] != "Demo Reviewer"
