import pytest
from pathlib import Path
from typer.testing import CliRunner
import ruamel.yaml
from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.models.scenario import Scenario
from aero_prop_logic_harness.services.guard_evaluator import GuardEvaluator, EvaluationError
from aero_prop_logic_harness.models.predicate import AtomicPredicate, PredicateOperator

yaml = ruamel.yaml.YAML(typ="safe")
runner = CliRunner()

def test_guard_evaluator_missing_signal():
    atomic = AtomicPredicate(
        operator=PredicateOperator.GT,
        signal_ref="IFACE-0001.test_sig",
        threshold=100.0
    )
    with pytest.raises(EvaluationError, match="Missing signal in snapshot for ref"):
        GuardEvaluator.evaluate(atomic, {})

def test_guard_evaluator_success():
    atomic = AtomicPredicate(
        operator=PredicateOperator.GT,
        signal_ref="IFACE-0001.test_sig",
        threshold=100.0
    )
    assert not GuardEvaluator.evaluate(atomic, {"IFACE-0001.test_sig": 50.0})
    assert GuardEvaluator.evaluate(atomic, {"IFACE-0001.test_sig": 150.0})

def test_signoff_unmanaged_rejected(tmp_path):
    result = runner.invoke(app, ["signoff-demo", "--dir", str(tmp_path), "--reviewer", "Test", "--resolution", "test"])
    assert result.exit_code == 1
    assert "Unmanaged Environment Error" in result.stdout


# NOTE: test_signoff_formal_rejected was removed from this file.
# The real test with monkeypatch-based assertions now lives in:
#   tests/test_phase3_signoff.py::TestSignoffFormalRejected::test_signoff_formal_rejected_via_monkeypatch
# Removing this stub closes TD-1 (no more false-positive empty-pass tests).


def test_schema_valid():
    yaml_data = """
    scenario_id: SCENARIO-001
    title: Test
    baseline_scope: demo-scale
    initial_mode_id: MODE-0001
    ticks:
      - tick_id: 1
        signal_updates:
          IFACE-0001.signal: 5
    """
    data = yaml.load(yaml_data)
    scenario = Scenario(**data)
    assert scenario.initial_mode_id == "MODE-0001"
    assert len(scenario.ticks) == 1
    

def test_engine_priority_conflict():
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine
    from aero_prop_logic_harness.models.scenario import ScenarioTick
    from aero_prop_logic_harness.models.transition import Transition
    from aero_prop_logic_harness.models.mode import Mode

    graph = ModeGraph()
    graph.nodes = {
        "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal"),
        "MODE-0002": Mode(id="MODE-0002", mode_type="normal", name="A"),
        "MODE-0003": Mode(id="MODE-0003", mode_type="normal", name="B"),
    }
    t1 = Transition(id="TRANS-0001", source_mode="MODE-0001", target_mode="MODE-0002", priority=1, name="T1")
    t2 = Transition(id="TRANS-0002", source_mode="MODE-0001", target_mode="MODE-0003", priority=1, name="T2")
    graph.edges = {"TRANS-0001": t1, "TRANS-0002": t2}
    graph._outgoing = {"MODE-0001": ["TRANS-0001", "TRANS-0002"]}

    engine = ScenarioEngine(graph)
    yaml_data = """
    scenario_id: SCENARIO-001
    title: Test
    baseline_scope: demo-scale
    initial_mode_id: MODE-0001
    ticks:
      - tick_id: 1
        signal_updates: {}
    """
    data = yaml.load(yaml_data)
    scenario = Scenario(**data)
    engine.run_scenario(scenario)
    assert engine.state.blocked_by_t2
    assert "Priority conflict" in engine.state.halt_reason

def test_engine_degraded_recovery():
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine
    from aero_prop_logic_harness.models.scenario import ScenarioTick
    from aero_prop_logic_harness.models.transition import Transition
    from aero_prop_logic_harness.models.mode import Mode

    graph = ModeGraph()
    graph.nodes = {
        "MODE-0001": Mode(id="MODE-0001", mode_type="degraded", name="Degraded"),
        "MODE-0002": Mode(id="MODE-0002", mode_type="emergency", name="Emergency"),
    }
    t1 = Transition(id="TRANS-0001", source_mode="MODE-0001", target_mode="MODE-0002", priority=1, name="T1")
    graph.edges = {"TRANS-0001": t1}
    graph._outgoing = {"MODE-0001": ["TRANS-0001"]}

    engine = ScenarioEngine(graph)
    yaml_data = """
    scenario_id: SCENARIO-001
    title: Test
    baseline_scope: demo-scale
    initial_mode_id: MODE-0001
    ticks:
      - tick_id: 1
        signal_updates: {}
    """
    data = yaml.load(yaml_data)
    scenario = Scenario(**data)
    engine.run_scenario(scenario)
    assert engine.state.blocked_by_t2
    assert "Degraded recovery conflict" in engine.state.halt_reason

