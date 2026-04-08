"""
Predicate grammar models for GUARD conditions.

Per PHASE2_ARCHITECTURE_PLAN §4.9:
  The authority field is ``predicate`` — a nested Pydantic object that is
  validated at load time.  No custom string parser required.  No evaluator
  required.

This module defines the minimal structured grammar:
  - AtomicPredicate: a single comparison against a signal value
  - CompoundPredicate: a boolean combination of predicates

IMPORTANT: These models are parse/validate/schema-export ONLY.
No evaluator or semantic execution engine is implemented (Phase 3+).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Signal reference pattern ──────────────────────────────────────────
# Must reference a declared interface signal: IFACE-NNNN.signal_name
SIGNAL_REF_PATTERN = re.compile(r"^IFACE-[0-9]{4}\.\w+$")


class PredicateOperator(str, Enum):
    """Comparison operators for atomic predicates.

    Phase 2A baseline (8 operators):
      GT, GE, LT, LE, EQ, NE, BOOL_TRUE, BOOL_FALSE

    Phase 3-3 additions (6 richer operators):
      DELTA_GT, DELTA_LT — signal change rate
      IN_RANGE           — value within [low, high]
      SUSTAINED_GT, SUSTAINED_LT — value sustained over N ticks
      HYSTERESIS_BAND    — set-point hysteresis with separate thresholds
    """
    # 2A baseline operators
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    EQ = "eq"
    NE = "ne"
    BOOL_TRUE = "bool_true"
    BOOL_FALSE = "bool_false"
    # Phase 3-3 richer operators
    DELTA_GT = "delta_gt"
    DELTA_LT = "delta_lt"
    IN_RANGE = "in_range"
    SUSTAINED_GT = "sustained_gt"
    SUSTAINED_LT = "sustained_lt"
    HYSTERESIS_BAND = "hysteresis_band"


# Operators that require a numeric/comparable threshold
_COMPARISON_OPS = {
    PredicateOperator.GT,
    PredicateOperator.GE,
    PredicateOperator.LT,
    PredicateOperator.LE,
    PredicateOperator.EQ,
    PredicateOperator.NE,
}

# Boolean-state operators (no threshold)
_BOOLEAN_OPS = {
    PredicateOperator.BOOL_TRUE,
    PredicateOperator.BOOL_FALSE,
}

# Phase 3-3: Richer operators requiring threshold + threshold_high
_RANGE_OPS = {
    PredicateOperator.IN_RANGE,
    PredicateOperator.HYSTERESIS_BAND,
}

# Phase 3-3: Delta operators (use threshold as delta threshold)
_DELTA_OPS = {
    PredicateOperator.DELTA_GT,
    PredicateOperator.DELTA_LT,
}

# Phase 3-3: Sustained operators (require threshold + duration_ticks)
_SUSTAINED_OPS = {
    PredicateOperator.SUSTAINED_GT,
    PredicateOperator.SUSTAINED_LT,
}

# Phase 3-3: All richer operators (handled by RicherEvaluator, not GuardEvaluator)
_RICHER_OPS = _RANGE_OPS | _DELTA_OPS | _SUSTAINED_OPS

# Hard cap on duration_ticks to prevent unbounded memory growth (§5.2.2)
_MAX_DURATION_TICKS = 100


class PredicateCombinator(str, Enum):
    """Boolean combinators for compound predicates."""
    AND = "and"
    OR = "or"
    NOT = "not"


class AtomicPredicate(BaseModel):
    """
    A single comparison of a signal value against a threshold.

    Examples (in YAML):
        predicate:
          predicate_type: "atomic"
          operator: "gt"
          signal_ref: "IFACE-0001.n2_speed"
          threshold: 95.0
          unit: "%"

        predicate:
          predicate_type: "atomic"
          operator: "bool_true"
          signal_ref: "IFACE-0002.fire_detected"

    Phase 3-3 additions (all Optional, backward compatible):
        threshold_high: upper bound for IN_RANGE / HYSTERESIS_BAND
        duration_ticks: sustain window for SUSTAINED_GT / SUSTAINED_LT
    """
    model_config = ConfigDict(extra="forbid")

    predicate_type: Literal["atomic"] = Field(
        default="atomic",
        description="Discriminator: always 'atomic' for AtomicPredicate",
    )
    operator: PredicateOperator = Field(
        description="Comparison operator",
    )
    signal_ref: str = Field(
        description="Signal reference in format IFACE-NNNN.signal_name",
    )
    threshold: Optional[float | int | bool] = Field(
        default=None,
        description="Comparison threshold (required for comparison ops, must be null for boolean ops)",
    )
    unit: str = Field(
        default="",
        description="Engineering unit of the threshold (e.g., '%', 'degC', 'rpm')",
    )
    # Phase 3-3 optional fields
    threshold_high: Optional[float | int] = Field(
        default=None,
        description="Upper threshold for IN_RANGE / HYSTERESIS_BAND (Phase 3-3)",
    )
    duration_ticks: Optional[int] = Field(
        default=None,
        description="Sustain window in ticks for SUSTAINED_GT / SUSTAINED_LT (Phase 3-3, max 100)",
    )

    @field_validator("signal_ref")
    @classmethod
    def check_signal_ref(cls, v: str) -> str:
        if not SIGNAL_REF_PATTERN.match(v):
            raise ValueError(
                f"Invalid signal_ref '{v}'. "
                f"Must match pattern IFACE-NNNN.signal_name"
            )
        return v

    @model_validator(mode="after")
    def check_threshold_consistency(self) -> "AtomicPredicate":
        """Validate threshold presence against operator type."""
        if self.operator in _COMPARISON_OPS:
            if self.threshold is None:
                raise ValueError(
                    f"Operator '{self.operator.value}' requires a non-null threshold"
                )
        elif self.operator in _BOOLEAN_OPS:
            if self.threshold is not None:
                raise ValueError(
                    f"Boolean operator '{self.operator.value}' must have null threshold, "
                    f"got {self.threshold!r}"
                )
        elif self.operator in _DELTA_OPS:
            if self.threshold is None:
                raise ValueError(
                    f"Delta operator '{self.operator.value}' requires a non-null threshold"
                )
        elif self.operator in _RANGE_OPS:
            if self.threshold is None or self.threshold_high is None:
                raise ValueError(
                    f"Range operator '{self.operator.value}' requires both "
                    f"threshold (low) and threshold_high"
                )
        elif self.operator in _SUSTAINED_OPS:
            if self.threshold is None:
                raise ValueError(
                    f"Sustained operator '{self.operator.value}' requires a non-null threshold"
                )
            if self.duration_ticks is None:
                raise ValueError(
                    f"Sustained operator '{self.operator.value}' requires duration_ticks"
                )
            if not (1 <= self.duration_ticks <= _MAX_DURATION_TICKS):
                raise ValueError(
                    f"duration_ticks must be 1..{_MAX_DURATION_TICKS}, "
                    f"got {self.duration_ticks}"
                )
        return self


class CompoundPredicate(BaseModel):
    """
    A boolean combination of predicates (AND/OR/NOT).

    Examples (in YAML):
        predicate:
          predicate_type: "compound"
          combinator: "and"
          operands:
            - predicate_type: "atomic"
              operator: "gt"
              signal_ref: "IFACE-0001.n2_speed"
              threshold: 95.0
            - predicate_type: "atomic"
              operator: "lt"
              signal_ref: "IFACE-0001.oil_pressure"
              threshold: 20.0
              unit: "psi"
    """
    model_config = ConfigDict(extra="forbid")

    predicate_type: Literal["compound"] = Field(
        default="compound",
        description="Discriminator: always 'compound' for CompoundPredicate",
    )
    combinator: PredicateCombinator = Field(
        description="Boolean combinator",
    )
    operands: list[Annotated[
        Union[AtomicPredicate, "CompoundPredicate"],
        Field(discriminator="predicate_type"),
    ]] = Field(
        description="Operands (predicates) to combine",
    )

    @model_validator(mode="after")
    def check_operand_count(self) -> "CompoundPredicate":
        """Validate operand count against combinator type."""
        n = len(self.operands)
        if self.combinator == PredicateCombinator.NOT:
            if n != 1:
                raise ValueError(
                    f"NOT combinator requires exactly 1 operand, got {n}"
                )
        else:  # AND / OR
            if n < 2:
                raise ValueError(
                    f"{self.combinator.value.upper()} combinator requires at least 2 operands, got {n}"
                )
        return self


# Rebuild model to resolve forward references
CompoundPredicate.model_rebuild()

# Union type for use in Guard model
PredicateExpression = Annotated[
    Union[AtomicPredicate, CompoundPredicate],
    Field(discriminator="predicate_type"),
]
