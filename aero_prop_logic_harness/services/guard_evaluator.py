from typing import Any, Dict
from aero_prop_logic_harness.models.predicate import (
    AtomicPredicate,
    CompoundPredicate,
    PredicateOperator,
    PredicateCombinator,
    PredicateExpression
)

class EvaluationError(Exception):
    """Raised when guard evaluation fails cleanly (e.g. missing signal)."""
    pass

class GuardEvaluator:
    """
    Evaluates predicate expressions safely against a signal snapshot.
    Strictly limited to Pydantic definitions. No string eval().
    """

    @classmethod
    def evaluate(cls, expression: PredicateExpression, snapshot: Dict[str, Any]) -> bool:
        if isinstance(expression, AtomicPredicate):
            return cls._evaluate_atomic(expression, snapshot)
        elif isinstance(expression, CompoundPredicate):
            return cls._evaluate_compound(expression, snapshot)
        else:
            raise TypeError(f"Unknown predicate type: {type(expression)}")

    @classmethod
    def _evaluate_atomic(cls, atomic: AtomicPredicate, snapshot: Dict[str, Any]) -> bool:
        if atomic.signal_ref not in snapshot:
            raise EvaluationError(f"Missing signal in snapshot for ref: {atomic.signal_ref}")
        
        current_value = snapshot[atomic.signal_ref]
        op = atomic.operator
        thres = atomic.threshold

        try:
            if op == PredicateOperator.EQ:
                return current_value == thres
            elif op == PredicateOperator.NE:
                return current_value != thres
            elif op == PredicateOperator.GT:
                return current_value > thres
            elif op == PredicateOperator.GE:
                return current_value >= thres
            elif op == PredicateOperator.LT:
                return current_value < thres
            elif op == PredicateOperator.LE:
                return current_value <= thres
            elif op == PredicateOperator.BOOL_TRUE:
                if not isinstance(current_value, bool):
                    raise EvaluationError(f"Signal {atomic.signal_ref} must be boolean for bool_true")
                return current_value is True
            elif op == PredicateOperator.BOOL_FALSE:
                if not isinstance(current_value, bool):
                    raise EvaluationError(f"Signal {atomic.signal_ref} must be boolean for bool_false")
                return current_value is False
            else:
                raise EvaluationError(f"Unsupported operator: {op}")
        except TypeError as e:
            raise EvaluationError(f"Type error during evaluation of {atomic.signal_ref}: {e}")

    @classmethod
    def _evaluate_compound(cls, compound: CompoundPredicate, snapshot: Dict[str, Any]) -> bool:
        comb = compound.combinator
        
        if comb == PredicateCombinator.NOT:
            # Pydantic validation ensures exactly 1 operand
            return not cls.evaluate(compound.operands[0], snapshot)
            
        elif comb == PredicateCombinator.AND:
            for op in compound.operands:
                if not cls.evaluate(op, snapshot):
                    return False
            return True
            
        elif comb == PredicateCombinator.OR:
            for op in compound.operands:
                if cls.evaluate(op, snapshot):
                    return True
            return False
            
        else:
            raise EvaluationError(f"Unsupported combinator: {comb}")
