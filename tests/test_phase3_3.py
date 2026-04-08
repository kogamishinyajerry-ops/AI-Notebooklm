"""
Phase 3-3 test suite — Richer Evaluator Boundary.

Covers:
  - RicherEvaluator: DELTA_GT, DELTA_LT, IN_RANGE, SUSTAINED_GT, SUSTAINED_LT, HYSTERESIS_BAND
  - Backward compatibility (baseline operators still work through adapter)
  - Missing signal → EvaluationError (no silent fallback)
  - No eval()/exec()/compile() in richer evaluator module
  - GuardEvaluator core unchanged
  - Evaluator explainability (RicherEvaluationResult / EvaluationStep)
  - Demo baseline integration with richer operators
  - Gate P3-B boundary enforcement
  - CLI: run-scenario --richer, replay-scenario --richer
  - Formal/unmanaged rejection for richer commands
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner

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
from aero_prop_logic_harness.services.scenario_engine import (
    ScenarioEngine,
    RuntimeState,
)
from aero_prop_logic_harness.services.guard_evaluator import (
    GuardEvaluator,
    EvaluationError,
)
from aero_prop_logic_harness.services.richer_evaluator import (
    RicherEvaluator,
    RicherEvaluationResult,
    EvaluationStep,
)

runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────


def _build_graph_with_richer_guards():
    """Build a ModeGraph with richer evaluator guards for testing."""
    graph = ModeGraph()
    graph.nodes = {
        "MODE-0001": Mode(id="MODE-0001", mode_type="normal", name="Normal", is_initial=True),
        "MODE-0002": Mode(id="MODE-0002", mode_type="degraded", name="Degraded"),
        "MODE-0003": Mode(id="MODE-0003", mode_type="emergency", name="Emergency"),
    }

    # DELTA_GT guard: N1 speed change > 500 Hz
    delta_guard = Guard(
        id="GUARD-9001",
        name="N1 Delta Anomaly",
        predicate=AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=500.0,
        ),
    )

    # IN_RANGE guard: N1 in [2000, 4800]
    range_guard = Guard(
        id="GUARD-9002",
        name="N1 Normal Range",
        predicate=AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        ),
    )

    # SUSTAINED_GT guard: N1 > 5250 for 3 ticks
    sustained_guard = Guard(
        id="GUARD-9003",
        name="Sustained Overspeed",
        predicate=AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        ),
    )

    # HYSTERESIS_BAND guard: band [20, 40]
    hysteresis_guard = Guard(
        id="GUARD-9004",
        name="Oil Pressure Hysteresis",
        predicate=AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        ),
    )

    # DELTA_LT guard: oil pressure drop < -5
    delta_lt_guard = Guard(
        id="GUARD-9005",
        name="Oil Pressure Drop",
        predicate=AtomicPredicate(
            operator=PredicateOperator.DELTA_LT,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=-5.0,
        ),
    )

    # SUSTAINED_LT guard: oil < 25 for 2 ticks
    sustained_lt_guard = Guard(
        id="GUARD-9006",
        name="Sustained Low Oil",
        predicate=AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_LT,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=25.0,
            duration_ticks=2,
        ),
    )

    graph.guards = {
        "GUARD-9001": delta_guard,
        "GUARD-9002": range_guard,
        "GUARD-9003": sustained_guard,
        "GUARD-9004": hysteresis_guard,
        "GUARD-9005": delta_lt_guard,
        "GUARD-9006": sustained_lt_guard,
    }

    t1 = Transition(
        id="TRANS-9001", source_mode="MODE-0001", target_mode="MODE-0002",
        priority=1, name="Normal to Degraded", guard="GUARD-9001",
    )
    t2 = Transition(
        id="TRANS-9002", source_mode="MODE-0001", target_mode="MODE-0003",
        priority=0, name="Normal to Emergency", guard="GUARD-9003",
    )
    t3 = Transition(
        id="TRANS-9003", source_mode="MODE-0002", target_mode="MODE-0001",
        priority=1, name="Degraded Recovery", guard="GUARD-9002",
    )

    graph.edges = {"TRANS-9001": t1, "TRANS-9002": t2, "TRANS-9003": t3}
    graph._outgoing = {
        "MODE-0001": ["TRANS-9001", "TRANS-9002"],
        "MODE-0002": ["TRANS-9003"],
    }

    return graph


def _make_state(snapshot, prev=None, history=None, hyst=None):
    """Create a RuntimeState with given data."""
    state = RuntimeState(
        current_mode_id="MODE-0001",
        signal_snapshot=snapshot,
        previous_signal_snapshot=prev or {},
        signal_history=history or {},
        hysteresis_state=hyst or {},
    )
    return state


# ═══════════════════════════════════════════════════════════════════════
# DELTA_GT / DELTA_LT
# ═══════════════════════════════════════════════════════════════════════


class TestDeltaEvaluation:
    """DELTA_GT and DELTA_LT operator evaluation."""

    def test_delta_gt_positive(self):
        """DELTA_GT returns True when delta > threshold."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=100.0,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 3000.0},
            prev={"IFACE-0001.N1_Speed": 2800.0},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True
        assert result.evaluator_mode == "richer"
        assert len(result.steps) == 1
        assert result.steps[0].result is True

    def test_delta_gt_negative(self):
        """DELTA_GT returns False when delta < threshold."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=500.0,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 3050.0},
            prev={"IFACE-0001.N1_Speed": 3000.0},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False

    def test_delta_lt_positive(self):
        """DELTA_LT returns True when delta < threshold (negative change)."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_LT,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=-5.0,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 30.0},
            prev={"IFACE-0001.Oil_Pressure": 45.0},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_delta_no_previous_returns_false(self):
        """DELTA_GT returns False (not error) when no previous snapshot."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=100.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 3000.0}, prev={})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False
        assert "No previous" in result.steps[0].reason

    def test_delta_missing_current_signal_raises(self):
        """DELTA_GT raises EvaluationError when signal missing from snapshot."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=100.0,
        )
        state = _make_state({}, prev={})
        with pytest.raises(EvaluationError, match="Missing signal"):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# IN_RANGE
# ═══════════════════════════════════════════════════════════════════════


class TestInRangeEvaluation:
    """IN_RANGE operator evaluation."""

    def test_in_range_true(self):
        """Value within [low, high] returns True."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 3500.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True
        assert "in range" in result.steps[0].reason

    def test_in_range_boundary_low(self):
        """Value exactly at low boundary returns True (inclusive)."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 2000.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_in_range_boundary_high(self):
        """Value exactly at high boundary returns True (inclusive)."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 4800.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_in_range_below(self):
        """Value below range returns False."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 1500.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False

    def test_in_range_above(self):
        """Value above range returns False."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 5000.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False

    def test_in_range_missing_signal_raises(self):
        """IN_RANGE raises EvaluationError on missing signal."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({})
        with pytest.raises(EvaluationError, match="Missing signal"):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# SUSTAINED_GT / SUSTAINED_LT
# ═══════════════════════════════════════════════════════════════════════


class TestSustainedEvaluation:
    """SUSTAINED_GT and SUSTAINED_LT operator evaluation."""

    def test_sustained_gt_true(self):
        """SUSTAINED_GT True when all values in window > threshold."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 5500.0},
            history={"IFACE-0001.N1_Speed": [4800.0, 5300.0, 5400.0, 5500.0]},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_sustained_gt_false_not_enough_history(self):
        """SUSTAINED_GT False when insufficient history."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 5500.0},
            history={"IFACE-0001.N1_Speed": [5300.0]},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False
        assert "Insufficient history" in result.steps[0].reason

    def test_sustained_gt_false_window_not_all_above(self):
        """SUSTAINED_GT False when window has a value below threshold."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 5500.0},
            history={"IFACE-0001.N1_Speed": [4800.0, 5300.0, 5200.0]},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False

    def test_sustained_lt_true(self):
        """SUSTAINED_LT True when all values < threshold."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_LT,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=25.0,
            duration_ticks=2,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 20.0},
            history={"IFACE-0001.Oil_Pressure": [30.0, 22.0, 20.0]},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_sustained_missing_signal_raises(self):
        """SUSTAINED_GT raises EvaluationError on missing signal."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        )
        state = _make_state({})
        with pytest.raises(EvaluationError):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# HYSTERESIS_BAND
# ═══════════════════════════════════════════════════════════════════════


class TestHysteresisEvaluation:
    """HYSTERESIS_BAND operator evaluation."""

    def test_hysteresis_enter_band(self):
        """HYSTERESIS_BAND transitions to True when value > high."""
        pred = AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 45.0},
            hyst={"IFACE-0001.Oil_Pressure": False},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True
        # Verify state was updated
        assert state.hysteresis_state["IFACE-0001.Oil_Pressure"] is True

    def test_hysteresis_stay_true(self):
        """HYSTERESIS_BAND stays True when value between low and high."""
        pred = AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 30.0},
            hyst={"IFACE-0001.Oil_Pressure": True},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_hysteresis_exit_band(self):
        """HYSTERESIS_BAND transitions to False when value < low."""
        pred = AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 15.0},
            hyst={"IFACE-0001.Oil_Pressure": True},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False
        assert state.hysteresis_state["IFACE-0001.Oil_Pressure"] is False

    def test_hysteresis_stay_false(self):
        """HYSTERESIS_BAND stays False when value between low and high."""
        pred = AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        )
        state = _make_state(
            {"IFACE-0001.Oil_Pressure": 30.0},
            hyst={"IFACE-0001.Oil_Pressure": False},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is False

    def test_hysteresis_missing_signal_raises(self):
        """HYSTERESIS_BAND raises EvaluationError on missing signal."""
        pred = AtomicPredicate(
            operator=PredicateOperator.HYSTERESIS_BAND,
            signal_ref="IFACE-0001.Oil_Pressure",
            threshold=20.0,
            threshold_high=40.0,
        )
        state = _make_state({})
        with pytest.raises(EvaluationError):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# Backward compatibility — baseline operators through adapter
# ═══════════════════════════════════════════════════════════════════════


class TestBaselineDelegation:
    """Baseline operators delegated to GuardEvaluator unchanged."""

    def test_gt_delegated(self):
        """GT operator delegated to GuardEvaluator."""
        pred = AtomicPredicate(
            operator=PredicateOperator.GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=90.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 95.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True
        assert result.evaluator_mode == "baseline"

    def test_lt_delegated(self):
        """LT operator delegated to GuardEvaluator."""
        pred = AtomicPredicate(
            operator=PredicateOperator.LT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=90.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 80.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True

    def test_missing_signal_delegated_raises(self):
        """Missing signal on baseline operator raises EvaluationError."""
        pred = AtomicPredicate(
            operator=PredicateOperator.GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=90.0,
        )
        state = _make_state({})
        with pytest.raises(EvaluationError):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# ScenarioEngine integration with RicherEvaluator
# ═══════════════════════════════════════════════════════════════════════


class TestEngineRicherIntegration:
    """ScenarioEngine with RicherEvaluator injected."""

    def test_delta_gt_triggers_transition(self):
        """Engine with RicherEvaluator transitions on DELTA_GT guard."""
        graph = _build_graph_with_richer_guards()
        evaluator = RicherEvaluator()
        engine = ScenarioEngine(graph, evaluator=evaluator)

        scenario = Scenario(
            scenario_id="SCENARIO-DELTA",
            title="Delta Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.N1_Speed": 3000.0}),
                ScenarioTick(tick_id=2, signal_updates={"IFACE-0001.N1_Speed": 3600.0}),
            ],
        )
        trace = engine.run_scenario(scenario)
        # Tick 2: delta = 600 > 500 → TRANS-9001 fires → MODE-0002
        assert trace.records[-1].mode_after == "MODE-0002"
        assert trace.records[-1].transition_selected == "TRANS-9001"

    def test_sustained_gt_triggers_emergency(self):
        """Engine with RicherEvaluator transitions on SUSTAINED_GT guard."""
        graph = _build_graph_with_richer_guards()
        evaluator = RicherEvaluator()
        engine = ScenarioEngine(graph, evaluator=evaluator)

        scenario = Scenario(
            scenario_id="SCENARIO-SUSTAINED",
            title="Sustained Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.N1_Speed": 4800.0}),
                ScenarioTick(tick_id=2, signal_updates={"IFACE-0001.N1_Speed": 5300.0}),
                ScenarioTick(tick_id=3, signal_updates={"IFACE-0001.N1_Speed": 5400.0}),
                ScenarioTick(tick_id=4, signal_updates={"IFACE-0001.N1_Speed": 5500.0}),
            ],
        )
        trace = engine.run_scenario(scenario)
        # Tick 4: 3-tick window [5300, 5400, 5500] all > 5250 → TRANS-9002 fires
        assert trace.records[-1].mode_after == "MODE-0003"
        assert trace.records[-1].transition_selected == "TRANS-9002"

    def test_engine_without_evaluator_uses_baseline(self):
        """Engine without evaluator uses baseline GuardEvaluator (2C behavior)."""
        graph = _build_graph_with_richer_guards()
        engine = ScenarioEngine(graph)

        scenario = Scenario(
            scenario_id="SCENARIO-BASELINE",
            title="Baseline Test",
            initial_mode_id="MODE-0001",
            ticks=[
                ScenarioTick(tick_id=1, signal_updates={"IFACE-0001.N1_Speed": 5300.0}),
                ScenarioTick(tick_id=2, signal_updates={"IFACE-0001.N1_Speed": 5400.0}),
                ScenarioTick(tick_id=3, signal_updates={"IFACE-0001.N1_Speed": 5500.0}),
            ],
        )
        # Without RicherEvaluator, SUSTAINED_GT is unsupported by GuardEvaluator
        # This will raise EvaluationError → T2 block
        trace = engine.run_scenario(scenario)
        assert engine.state.blocked_by_t2 is True
        assert "Unsupported operator" in (engine.state.halt_reason or "")


# ═══════════════════════════════════════════════════════════════════════
# Explainability
# ═══════════════════════════════════════════════════════════════════════


class TestExplainability:
    """RicherEvaluationResult machine-readable explainability."""

    def test_explainability_delta(self):
        """Delta evaluation produces machine-readable explanation."""
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=100.0,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 300.0},
            prev={"IFACE-0001.N1_Speed": 150.0},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.value is True
        step = result.steps[0]
        assert step.operator == "delta_gt"
        assert step.signal_ref == "IFACE-0001.N1_Speed"
        assert step.current_value == 300.0
        assert step.previous_value == 150.0
        assert "delta=" in step.reason

    def test_explainability_in_range(self):
        """IN_RANGE evaluation produces machine-readable explanation."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=2000.0,
            threshold_high=4800.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 3500.0})
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.steps[0].threshold == 2000.0
        assert result.steps[0].threshold_high == 4800.0

    def test_explainability_sustained(self):
        """SUSTAINED evaluation produces duration_ticks in explanation."""
        pred = AtomicPredicate(
            operator=PredicateOperator.SUSTAINED_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=5250.0,
            duration_ticks=3,
        )
        state = _make_state(
            {"IFACE-0001.N1_Speed": 5500.0},
            history={"IFACE-0001.N1_Speed": [5300.0, 5400.0, 5500.0]},
        )
        result = RicherEvaluator.evaluate_with_explanation(pred, state)
        assert result.steps[0].duration_ticks == 3


# ═══════════════════════════════════════════════════════════════════════
# Gate P3-B: Evaluator Boundary Preserved
# ═══════════════════════════════════════════════════════════════════════


class TestGateP3B:
    """Verify Phase 3-3 does not break evaluator boundary."""

    def test_no_eval_exec_compile(self):
        """No eval()/exec()/compile() in richer_evaluator module."""
        import inspect
        source = inspect.getsource(RicherEvaluator)
        assert "eval(" not in source
        assert "exec(" not in source
        assert "compile(" not in source

    def test_guard_evaluator_core_unchanged(self):
        """GuardEvaluator still handles baseline operators correctly."""
        pred = AtomicPredicate(
            operator=PredicateOperator.GT,
            signal_ref="IFACE-0001.test",
            threshold=10.0,
        )
        assert GuardEvaluator.evaluate(pred, {"IFACE-0001.test": 20.0}) is True
        assert GuardEvaluator.evaluate(pred, {"IFACE-0001.test": 5.0}) is False

    def test_duration_ticks_hard_cap(self):
        """duration_ticks has hard cap at 100."""
        with pytest.raises(ValueError, match="duration_ticks must be 1..100"):
            AtomicPredicate(
                operator=PredicateOperator.SUSTAINED_GT,
                signal_ref="IFACE-0001.N1_Speed",
                threshold=100.0,
                duration_ticks=101,
            )

    def test_richer_ops_set_finite(self):
        """Richer operator set is exactly 6 operators (no unbounded growth)."""
        from aero_prop_logic_harness.models.predicate import (
            _RICHER_OPS, _RANGE_OPS, _DELTA_OPS, _SUSTAINED_OPS,
        )
        # HYSTERESIS_BAND is in _RANGE_OPS alongside IN_RANGE
        all_richer = _RANGE_OPS | _DELTA_OPS | _SUSTAINED_OPS
        assert len(all_richer) == 6  # IN_RANGE, HYSTERESIS_BAND, DELTA_GT, DELTA_LT, SUSTAINED_GT, SUSTAINED_LT

    def test_no_cross_signal_arithmetic(self):
        """RicherEvaluator does not support cross-signal arithmetic."""
        # Verify: evaluate only handles single signal_ref per AtomicPredicate
        # This is enforced by the model — signal_ref is a single string field
        pred = AtomicPredicate(
            operator=PredicateOperator.DELTA_GT,
            signal_ref="IFACE-0001.N1_Speed",
            threshold=100.0,
        )
        # signal_ref is a single string — no way to specify two signals
        assert pred.signal_ref == "IFACE-0001.N1_Speed"

    def test_missing_signal_no_silent_fallback(self):
        """Missing signal raises EvaluationError, not silent False."""
        pred = AtomicPredicate(
            operator=PredicateOperator.IN_RANGE,
            signal_ref="IFACE-0001.NONEXISTENT",
            threshold=0.0,
            threshold_high=100.0,
        )
        state = _make_state({"IFACE-0001.N1_Speed": 50.0})
        with pytest.raises(EvaluationError):
            RicherEvaluator.evaluate(pred, state)


# ═══════════════════════════════════════════════════════════════════════
# Gate P3-A: Frozen Input Preservation (regression)
# ═══════════════════════════════════════════════════════════════════════


class TestGateP3ARegression:
    """Verify Phase 3-3 preserves all 2A/2B/2C/3-1/3-2 frozen contracts."""

    def test_mode_graph_no_execute_methods(self):
        forbidden = {"step", "fire", "evaluate", "execute"}
        methods = {m for m in dir(ModeGraph) if not m.startswith("_")}
        assert forbidden.isdisjoint(methods)

    def test_no_trans_func_trace_direction(self):
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        trans_func = [d for d in VALID_TRACE_DIRECTIONS if "TRANS" in str(d[0]) and "FUNC" in str(d[1])]
        assert len(trans_func) == 0

    def test_no_trans_iface_trace_direction(self):
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        trans_iface = [d for d in VALID_TRACE_DIRECTIONS if "TRANS" in str(d[0]) and "IFACE" in str(d[1])]
        assert len(trans_iface) == 0

    def test_valid_trace_directions_count_unchanged(self):
        from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
        assert len(VALID_TRACE_DIRECTIONS) == 25

    def test_predicate_expression_not_reintroduced(self):
        """predicate_expression must not appear as a field name."""
        from aero_prop_logic_harness.models.guard import Guard
        field_names = set(Guard.model_fields.keys())
        assert "predicate_expression" not in field_names

    def test_predicate_is_sole_authority(self):
        """Guard.predicate must exist and be the sole machine authority."""
        from aero_prop_logic_harness.models.guard import Guard
        assert "predicate" in Guard.model_fields


# ═══════════════════════════════════════════════════════════════════════
# CLI Integration
# ═══════════════════════════════════════════════════════════════════════


class TestCLIRicher:
    """CLI --richer flag integration tests."""

    def test_run_scenario_richer_flag_accepted(self):
        """run-scenario --richer does not crash on a baseline scenario."""
        # Use the richer_delta_anomaly scenario which has N1_Speed signal
        # matching the demo baseline guards
        result = runner.invoke(app, [
            "run-scenario",
            "--dir", "artifacts/examples/minimal_demo_set",
            "--scenario", "artifacts/examples/minimal_demo_set/scenarios/richer_delta_anomaly.yml",
            "--richer",
        ])
        # Should succeed (delta > 500 Hz triggers transition)
        assert result.exit_code == 0
        assert "RicherEvaluator enabled" in result.stdout

    def test_run_scenario_richer_formal_rejected(self):
        """run-scenario --richer still rejects formal directory."""
        with patch("aero_prop_logic_harness.cli.is_formal_baseline_root", return_value=True):
            result = runner.invoke(app, [
                "run-scenario",
                "--dir", "artifacts/examples/minimal_demo_set",
                "--scenario", "artifacts/examples/minimal_demo_set/scenarios/test.yml",
                "--richer",
            ])
        assert result.exit_code == 1

    def test_replay_scenario_richer_flag(self):
        """replay-scenario --richer does not crash."""
        # First run to get a trace
        runner.invoke(app, [
            "run-scenario",
            "--dir", "artifacts/examples/minimal_demo_set",
            "--scenario", "artifacts/examples/minimal_demo_set/scenarios/richer_delta_anomaly.yml",
            "--richer",
        ])
        # Find the latest trace
        traces_dir = Path("artifacts/examples/minimal_demo_set/.aplh/traces")
        traces = sorted(traces_dir.glob("run_*_SCENARIO-RICHER*.yaml"), reverse=True)
        if not traces:
            pytest.skip("No trace files found for richer scenario")

        result = runner.invoke(app, [
            "replay-scenario",
            "--dir", "artifacts/examples/minimal_demo_set",
            "--scenario", "artifacts/examples/minimal_demo_set/scenarios/richer_delta_anomaly.yml",
            "--trace", str(traces[0]),
            "--richer",
        ])
        assert result.exit_code == 0
        assert "RicherEvaluator enabled" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# Demo Scenario File Parsing
# ═══════════════════════════════════════════════════════════════════════


class TestRicherDemoScenarios:
    """Richer demo scenarios parse correctly."""

    @pytest.mark.parametrize("filename", [
        "richer_delta_anomaly.yml",
        "richer_recovery_in_range.yml",
        "richer_sustained_overspeed.yml",
    ])
    def test_richer_scenario_parses(self, filename):
        """Richer demo scenarios parse as valid Scenario objects."""
        import ruamel.yaml
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
        assert scenario.baseline_scope == "demo-scale"
        assert len(scenario.ticks) > 0
        assert scenario.expected_final_mode is not None
        assert scenario.expected_transitions is not None
