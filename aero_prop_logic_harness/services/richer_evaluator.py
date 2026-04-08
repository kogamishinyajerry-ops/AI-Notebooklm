"""
Richer Guard Evaluator adapter (Phase 3-3).

Outer adapter layer that extends the 2C GuardEvaluator with 6 additional
operators for demo-scale scenarios:

  DELTA_GT / DELTA_LT — signal change between ticks
  IN_RANGE            — value within [low, high]
  SUSTAINED_GT / SUSTAINED_LT — value sustained over N ticks
  HYSTERESIS_BAND     — asymmetric thresholds with state memory

Architecture:
  - Delegates baseline operators (GT, GE, LT, LE, EQ, NE, BOOL_*) to
    the unchanged GuardEvaluator core.
  - Handles richer operators in this adapter layer.
  - Reads signal_history / previous_signal_snapshot / hysteresis_state
    from RuntimeState — never from ModeGraph or validators.

Per PHASE3_ARCHITECTURE_PLAN §5.2:
  - NOT a general DSL platform
  - NO eval() / exec() / compile()
  - NO cross-signal arithmetic
  - NO PID / integral / derivative logic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aero_prop_logic_harness.models.predicate import (
    AtomicPredicate,
    CompoundPredicate,
    PredicateCombinator,
    PredicateOperator,
    PredicateExpression,
    _COMPARISON_OPS,
    _BOOLEAN_OPS,
    _DELTA_OPS,
    _RANGE_OPS,
    _SUSTAINED_OPS,
    _MAX_DURATION_TICKS,
)
from aero_prop_logic_harness.services.guard_evaluator import (
    GuardEvaluator,
    EvaluationError,
)


# ── Explainability structures ──────────────────────────────────────────


@dataclass
class EvaluationStep:
    """A single atomic evaluation result within a richer evaluation."""
    operator: str
    signal_ref: str
    threshold: Optional[Any]
    threshold_high: Optional[Any] = None
    duration_ticks: Optional[int] = None
    current_value: Optional[Any] = None
    previous_value: Optional[Any] = None
    result: bool = False
    reason: str = ""


@dataclass
class RicherEvaluationResult:
    """Structured result from RicherEvaluator, including explainability."""
    value: bool
    evaluator_mode: str  # "baseline" or "richer"
    steps: List[EvaluationStep] = field(default_factory=list)
    error: Optional[str] = None


# ── RicherEvaluator ────────────────────────────────────────────────────


class RicherEvaluator:
    """Outer adapter that extends GuardEvaluator with richer operators.

    Per §5.2.4 of the architecture plan:
      - For baseline operators, delegates to GuardEvaluator unchanged.
      - For richer operators (DELTA_*, IN_RANGE, SUSTAINED_*, HYSTERESIS_BAND),
        evaluates in this adapter layer using RuntimeState extensions.
      - GuardEvaluator core code is NEVER modified.

    State dependencies (read from RuntimeState, not stored here):
      - signal_snapshot: current tick signal values
      - previous_signal_snapshot: prior tick signal values (for DELTA_*)
      - signal_history: rolling window per signal (for SUSTAINED_*)
      - hysteresis_state: per-signal boolean state (for HYSTERESIS_BAND)
    """

    @classmethod
    def evaluate(
        cls,
        expression: PredicateExpression,
        runtime_state: Any,
    ) -> bool:
        """Evaluate a predicate expression against RuntimeState.

        For baseline operators, delegates to GuardEvaluator.
        For richer operators, evaluates in this adapter layer.

        Args:
            expression: The predicate to evaluate.
            runtime_state: A RuntimeState object with signal_snapshot,
                previous_signal_snapshot, signal_history, hysteresis_state.

        Returns:
            bool result of the evaluation.

        Raises:
            EvaluationError: On missing signal or type error.
        """
        result = cls.evaluate_with_explanation(expression, runtime_state)
        if result.error:
            raise EvaluationError(result.error)
        return result.value

    @classmethod
    def evaluate_with_explanation(
        cls,
        expression: PredicateExpression,
        runtime_state: Any,
    ) -> RicherEvaluationResult:
        """Evaluate with structured explainability output.

        Returns a RicherEvaluationResult with machine-readable explanation.
        """
        if isinstance(expression, AtomicPredicate):
            return cls._evaluate_atomic(expression, runtime_state)
        elif isinstance(expression, CompoundPredicate):
            return cls._evaluate_compound(expression, runtime_state)
        else:
            return RicherEvaluationResult(
                value=False,
                evaluator_mode="richer",
                error=f"Unknown predicate type: {type(expression)}",
            )

    # ── Atomic evaluation ────────────────────────────────────────────

    @classmethod
    def _evaluate_atomic(
        cls,
        atomic: AtomicPredicate,
        state: Any,
    ) -> RicherEvaluationResult:
        op = atomic.operator

        # Delegate baseline operators to GuardEvaluator
        if op in _COMPARISON_OPS or op in _BOOLEAN_OPS:
            try:
                result = GuardEvaluator.evaluate(
                    atomic, state.signal_snapshot
                )
                return RicherEvaluationResult(
                    value=result,
                    evaluator_mode="baseline",
                    steps=[EvaluationStep(
                        operator=op.value,
                        signal_ref=atomic.signal_ref,
                        threshold=atomic.threshold,
                        current_value=state.signal_snapshot.get(atomic.signal_ref),
                        result=result,
                        reason="Delegated to GuardEvaluator (baseline operator)",
                    )],
                )
            except EvaluationError as e:
                return RicherEvaluationResult(
                    value=False,
                    evaluator_mode="baseline",
                    error=str(e),
                )

        # Richer operators — handled here
        snapshot = state.signal_snapshot

        try:
            if op in _DELTA_OPS:
                return cls._eval_delta(atomic, state)
            elif op == PredicateOperator.IN_RANGE:
                return cls._eval_in_range(atomic, snapshot)
            elif op in _SUSTAINED_OPS:
                return cls._eval_sustained(atomic, state)
            elif op == PredicateOperator.HYSTERESIS_BAND:
                return cls._eval_hysteresis(atomic, state)
            else:
                return RicherEvaluationResult(
                    value=False,
                    evaluator_mode="richer",
                    error=f"Unknown richer operator: {op}",
                )
        except Exception as e:
            if isinstance(e, EvaluationError):
                raise
            raise EvaluationError(
                f"Richer evaluation error for {atomic.signal_ref}: {e}"
            )

    # ── DELTA_GT / DELTA_LT ─────────────────────────────────────────

    @classmethod
    def _eval_delta(
        cls,
        atomic: AtomicPredicate,
        state: Any,
    ) -> RicherEvaluationResult:
        sig = atomic.signal_ref
        threshold = float(atomic.threshold)

        current = state.signal_snapshot.get(sig)
        previous = state.previous_signal_snapshot.get(sig)

        if current is None:
            raise EvaluationError(
                f"Missing signal '{sig}' in current snapshot for DELTA evaluation"
            )

        # If no previous snapshot, delta is undefined → explicit failure
        if previous is None:
            return RicherEvaluationResult(
                value=False,
                evaluator_mode="richer",
                steps=[EvaluationStep(
                    operator=atomic.operator.value,
                    signal_ref=sig,
                    threshold=threshold,
                    current_value=current,
                    previous_value=None,
                    result=False,
                    reason="No previous signal value — delta undefined on first tick",
                )],
            )

        delta = float(current) - float(previous)
        op = atomic.operator

        if op == PredicateOperator.DELTA_GT:
            result = delta > threshold
        else:  # DELTA_LT
            result = delta < threshold

        return RicherEvaluationResult(
            value=result,
            evaluator_mode="richer",
            steps=[EvaluationStep(
                operator=op.value,
                signal_ref=sig,
                threshold=threshold,
                current_value=current,
                previous_value=previous,
                result=result,
                reason=(
                    f"delta={delta:.4g}, threshold={threshold}, "
                    f"operator={op.value} → {'true' if result else 'false'}"
                ),
            )],
        )

    # ── IN_RANGE ─────────────────────────────────────────────────────

    @classmethod
    def _eval_in_range(
        cls,
        atomic: AtomicPredicate,
        snapshot: Dict[str, Any],
    ) -> RicherEvaluationResult:
        sig = atomic.signal_ref
        low = float(atomic.threshold)
        high = float(atomic.threshold_high)

        if sig not in snapshot:
            raise EvaluationError(
                f"Missing signal '{sig}' for IN_RANGE evaluation"
            )

        value = float(snapshot[sig])
        result = low <= value <= high

        return RicherEvaluationResult(
            value=result,
            evaluator_mode="richer",
            steps=[EvaluationStep(
                operator="in_range",
                signal_ref=sig,
                threshold=low,
                threshold_high=high,
                current_value=value,
                result=result,
                reason=(
                    f"value={value}, range=[{low}, {high}] → "
                    f"{'in range' if result else 'out of range'}"
                ),
            )],
        )

    # ── SUSTAINED_GT / SUSTAINED_LT ──────────────────────────────────

    @classmethod
    def _eval_sustained(
        cls,
        atomic: AtomicPredicate,
        state: Any,
    ) -> RicherEvaluationResult:
        sig = atomic.signal_ref
        threshold = float(atomic.threshold)
        duration = atomic.duration_ticks
        op = atomic.operator

        if sig not in state.signal_snapshot:
            raise EvaluationError(
                f"Missing signal '{sig}' for SUSTAINED evaluation"
            )

        history = state.signal_history.get(sig, [])

        # Need at least `duration` entries in history
        if len(history) < duration:
            return RicherEvaluationResult(
                value=False,
                evaluator_mode="richer",
                steps=[EvaluationStep(
                    operator=op.value,
                    signal_ref=sig,
                    threshold=threshold,
                    duration_ticks=duration,
                    current_value=state.signal_snapshot[sig],
                    result=False,
                    reason=(
                        f"Insufficient history: need {duration} ticks, "
                        f"have {len(history)}"
                    ),
                )],
            )

        # Check the last `duration` entries
        window = history[-duration:]

        if op == PredicateOperator.SUSTAINED_GT:
            result = all(float(v) > threshold for v in window)
            cmp_desc = f"all > {threshold}"
        else:  # SUSTAINED_LT
            result = all(float(v) < threshold for v in window)
            cmp_desc = f"all < {threshold}"

        return RicherEvaluationResult(
            value=result,
            evaluator_mode="richer",
            steps=[EvaluationStep(
                operator=op.value,
                signal_ref=sig,
                threshold=threshold,
                duration_ticks=duration,
                current_value=state.signal_snapshot[sig],
                result=result,
                reason=(
                    f"Window of {duration} ticks: {cmp_desc} → "
                    f"{'sustained' if result else 'not sustained'}"
                ),
            )],
        )

    # ── HYSTERESIS_BAND ──────────────────────────────────────────────

    @classmethod
    def _eval_hysteresis(
        cls,
        atomic: AtomicPredicate,
        state: Any,
    ) -> RicherEvaluationResult:
        sig = atomic.signal_ref
        low = float(atomic.threshold)
        high = float(atomic.threshold_high)

        if sig not in state.signal_snapshot:
            raise EvaluationError(
                f"Missing signal '{sig}' for HYSTERESIS_BAND evaluation"
            )

        value = float(state.signal_snapshot[sig])
        current_state = state.hysteresis_state.get(sig, False)

        # Hysteresis logic:
        # - If currently False (below band): become True only when value > high
        # - If currently True (above band): become False only when value < low
        if not current_state:
            new_state = value > high
            transition = f"value={value} > high={high} → {new_state}"
        else:
            new_state = not (value < low)
            if value < low:
                transition = f"value={value} < low={low} → false (exit band)"
            else:
                transition = f"value={value} >= low={low} → staying true"

        # Update hysteresis state
        state.hysteresis_state[sig] = new_state

        return RicherEvaluationResult(
            value=new_state,
            evaluator_mode="richer",
            steps=[EvaluationStep(
                operator="hysteresis_band",
                signal_ref=sig,
                threshold=low,
                threshold_high=high,
                current_value=value,
                result=new_state,
                reason=(
                    f"band=[{low}, {high}], value={value}, "
                    f"prev_state={'in' if current_state else 'out'}, "
                    f"{transition}"
                ),
            )],
        )

    # ── Compound evaluation ──────────────────────────────────────────

    @classmethod
    def _evaluate_compound(
        cls,
        compound: CompoundPredicate,
        state: Any,
    ) -> RicherEvaluationResult:
        combinator = compound.combinator

        if combinator == PredicateCombinator.NOT:
            operand_result = cls.evaluate_with_explanation(
                compound.operands[0], state
            )
            if operand_result.error:
                return operand_result
            return RicherEvaluationResult(
                value=not operand_result.value,
                evaluator_mode=operand_result.evaluator_mode,
                steps=operand_result.steps,
            )

        elif combinator == PredicateCombinator.AND:
            all_steps: List[EvaluationStep] = []
            for operand in compound.operands:
                op_result = cls.evaluate_with_explanation(operand, state)
                if op_result.error:
                    return op_result
                all_steps.extend(op_result.steps)
                if not op_result.value:
                    return RicherEvaluationResult(
                        value=False,
                        evaluator_mode="richer",
                        steps=all_steps,
                    )
            return RicherEvaluationResult(
                value=True,
                evaluator_mode="richer",
                steps=all_steps,
            )

        elif combinator == PredicateCombinator.OR:
            all_steps = []
            for operand in compound.operands:
                op_result = cls.evaluate_with_explanation(operand, state)
                if op_result.error:
                    return op_result
                all_steps.extend(op_result.steps)
                if op_result.value:
                    return RicherEvaluationResult(
                        value=True,
                        evaluator_mode="richer",
                        steps=all_steps,
                    )
            return RicherEvaluationResult(
                value=False,
                evaluator_mode="richer",
                steps=all_steps,
            )

        else:
            return RicherEvaluationResult(
                value=False,
                evaluator_mode="richer",
                error=f"Unknown combinator: {combinator}",
            )
