"""
Guard data model (Phase 2A).

A Guard represents a boolean predicate that conditions a state transition.
The ``predicate`` field is the **sole machine-checkable authority** (§4.7).
The ``description`` field provides a human-readable summary and is
explicitly NOT machine-checkable (§4.7 R3 freeze note).

Per PHASE2_ARCHITECTURE_PLAN §4.3 + §4.9 grammar.

IMPORTANT: ``predicate_expression`` is a superseded working name.
Only ``predicate`` is valid (§4.7 R3 freeze).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .common import ArtifactBase, ArtifactType
from .predicate import PredicateExpression


class InputSignalRef(BaseModel):
    """
    Convenience cross-reference to a signal used by this guard.

    This is informational — the authoritative signal binding is in
    ``predicate.signal_ref`` for each AtomicPredicate leaf.
    """
    model_config = ConfigDict(extra="forbid")

    interface: str = Field(
        description="IFACE-xxxx ID of the interface",
    )
    signal: str = Field(
        description="Signal name within the interface",
    )
    unit: str = Field(
        default="",
        description="Expected engineering unit",
    )


class Guard(ArtifactBase):
    """
    Guard condition artifact for propulsion control logic.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.GUARD,
        description="Must be 'guard'",
    )
    name: str = Field(
        description="Guard condition name",
    )
    description: str = Field(
        default="",
        description="Human-readable summary of the guard condition "
                    "(NOT the machine-checkable authority — see §4.7)",
    )

    # THE machine-checkable authority (§4.7, §4.9)
    predicate: PredicateExpression = Field(
        description="Structured predicate: the sole machine-checkable authority "
                    "for this guard condition (AtomicPredicate | CompoundPredicate)",
    )

    # Convenience cross-references
    input_signals: list[InputSignalRef] = Field(
        default_factory=list,
        description="Informational cross-references to signals used by predicates",
    )
    related_interfaces: list[str] = Field(
        default_factory=list,
        description="IFACE-xxxx IDs of interfaces referenced by this guard",
    )
    related_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs related to this guard condition",
    )
    related_abnormals: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs related to this guard condition",
    )

    # §2.7 reciprocal field
    used_by_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs that reference this guard",
    )
