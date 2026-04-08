import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from aero_prop_logic_harness.models.scenario import Scenario, ScenarioTick
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.services.guard_evaluator import GuardEvaluator, EvaluationError
from aero_prop_logic_harness.services.decision_tracer import DecisionTrace, TransitionRecord

class RuntimeState(BaseModel):
    """Isolated state container for scenario execution.

    Phase 3-3 additions:
      - previous_signal_snapshot: prior tick's signal values (for DELTA_* ops)
      - signal_history: rolling window per signal (for SUSTAINED_* ops)
      - hysteresis_state: per-signal boolean state (for HYSTERESIS_BAND)
    """
    model_config = ConfigDict(extra="forbid")

    current_mode_id: str
    signal_snapshot: Dict[str, Any] = {}
    current_tick: int = 0
    halt_reason: Optional[str] = None
    blocked_by_t2: bool = False
    # Phase 3-3: richer evaluator state
    previous_signal_snapshot: Dict[str, Any] = {}
    signal_history: Dict[str, List[Any]] = {}
    hysteresis_state: Dict[str, bool] = {}

class ScenarioEngine:
    """
    Demo-scale scenario runtime dispatcher.
    Reads tick streams, resolves transitions via ModeGraph, evaluates guards,
    and updates isolated RuntimeState. Never pollutes ModeGraph.

    Phase 3: generates a unique ``run_id`` per execution for audit correlation.
    Phase 3-3: accepts optional ``evaluator`` parameter for richer evaluation.
               When None, uses the 2C GuardEvaluator (baseline behavior).
    """
    def __init__(self, graph: ModeGraph, evaluator=None) -> None:
        self.graph = graph
        self._evaluator = evaluator  # Phase 3-3: optional RicherEvaluator
        self.state: Optional[RuntimeState] = None
        self.trace: Optional[DecisionTrace] = None
        self.run_id: Optional[str] = None

    @staticmethod
    def generate_run_id() -> str:
        """Generate a unique run identifier for audit correlation."""
        return f"RUN-{uuid.uuid4().hex[:12].upper()}"

    def run_scenario(
        self,
        scenario: Scenario,
        run_id: Optional[str] = None,
    ) -> DecisionTrace:
        """Runs the entire scenario and returns the decision trace.

        Args:
            scenario: The scenario to execute.
            run_id: Optional override for the run identifier.
                    If not provided, a new unique run_id is generated.
        """
        self.run_id = run_id or self.generate_run_id()
        self.state = RuntimeState(current_mode_id=scenario.initial_mode_id)
        self.trace = DecisionTrace(
            run_id=self.run_id,
            scenario_id=scenario.scenario_id,
        )
        
        for tick in scenario.ticks:
            if self.state.blocked_by_t2:
                # Keep outputting block record if halted
                break
                
            self._step_tick(tick)
            
        return self.trace
        
    def _step_tick(self, tick: ScenarioTick) -> None:
        # Phase 3-3: snapshot previous signals before update
        self.state.previous_signal_snapshot = dict(self.state.signal_snapshot)
        # Update signals
        self.state.signal_snapshot.update(tick.signal_updates)
        self.state.current_tick = tick.tick_id
        # Phase 3-3: maintain signal history for SUSTAINED_* operators
        for sig_ref, value in self.state.signal_snapshot.items():
            if sig_ref not in self.state.signal_history:
                self.state.signal_history[sig_ref] = []
            self.state.signal_history[sig_ref].append(value)
        
        mode_before = self.state.current_mode_id
        
        # 1. Get candidate transitions
        out_trans_ids = self.graph.transitions_from(mode_before)
        candidates = []
        
        for t_id in out_trans_ids:
            trans = self.graph.edges[t_id]
            if not trans.guard:
                # Unguarded transition is always eligible
                candidates.append(trans)
                continue
                
            guard = self.graph.guards.get(trans.guard)
            if not guard:
                self.state.halt_reason = f"TRANS {t_id} references a missing GUARD {trans.guard}"
                self.state.blocked_by_t2 = True
                self._record(tick.tick_id, mode_before, out_trans_ids)
                return
                
            # Evaluate — Phase 3-3: delegate to injected evaluator if present
            try:
                if self._evaluator is not None:
                    result = self._evaluator.evaluate(
                        guard.predicate, self.state
                    )
                else:
                    result = GuardEvaluator.evaluate(
                        guard.predicate, self.state.signal_snapshot
                    )
                if result:
                    candidates.append(trans)
            except EvaluationError as e:
                # In 2C strictly fail instead of bypass
                self.state.halt_reason = f"Evaluation failed for guard {trans.guard}: {e}"
                self.state.blocked_by_t2 = True
                self._record(tick.tick_id, mode_before, out_trans_ids)
                return

        # 2. Priority check
        if not candidates:
            # No transition satisfied
            self._record(tick.tick_id, mode_before, out_trans_ids)
            return
            
        # Group by priority (lower number == higher priority)
        # Assuming priority is integer, if None, assume a default high number
        # Note: Model transition has `priority: int = 1`
        highest_priority = min(c.priority for c in candidates)
        winners = [c for c in candidates if c.priority == highest_priority]
        
        if len(winners) > 1:
            self.state.halt_reason = (
                f"Priority conflict [T2 Blocked]: multiple transitions {','.join(c.id for c in winners)} "
                f"share priority {highest_priority}"
            )
            self.state.blocked_by_t2 = True
            self._record(tick.tick_id, mode_before, out_trans_ids)
            return
            
        winner = winners[0]
        
        # 3. Apply transition
        mode_after = winner.target_mode
        
        # Check T2 Degraded Recovery condition
        curr_mode_obj = self.graph.nodes[mode_before]
        next_mode_obj = self.graph.nodes[mode_after]
        
        if curr_mode_obj.mode_type == "degraded" and next_mode_obj.mode_type != "normal":
            self.state.halt_reason = (
                f"Degraded recovery conflict [T2 Blocked]: leaving degraded mode {mode_before} "
                f"but target {mode_after} is {next_mode_obj.mode_type}, not normal."
            )
            self.state.blocked_by_t2 = True
            self._record(tick.tick_id, mode_before, out_trans_ids)
            return

        # Emitted actions (just records, NO execution)
        emitted_actions = list(winner.actions)
        
        self._record(
            tick.tick_id, 
            mode_before, 
            out_trans_ids, 
            transition_selected=winner.id,
            mode_after=mode_after,
            actions_emitted=emitted_actions
        )
        
        # Finally, update state mode
        self.state.current_mode_id = mode_after
        
    def _record(self, tick_id: int, mode_before: str, candidates: List[str], 
                transition_selected: Optional[str] = None, mode_after: Optional[str] = None, 
                actions_emitted: Optional[List[str]] = None) -> None:
        rec = TransitionRecord(
            tick_id=tick_id,
            applied_signals=dict(self.state.signal_snapshot),
            mode_before=mode_before,
            candidates_considered=candidates,
            transition_selected=transition_selected,
            mode_after=mode_after or mode_before,
            actions_emitted=actions_emitted or [],
            block_reason=self.state.halt_reason,
            run_id=self.run_id,
            scenario_id=self.trace.scenario_id if self.trace else None,
        )
        self.trace.add_record(rec)

