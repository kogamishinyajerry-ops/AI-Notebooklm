"""
Transition data model (Phase 2A).

A Transition represents a directed state change between two Modes.
It captures the trigger, guard condition, priority for arbitration,
and optional actions.

Per PHASE2_ARCHITECTURE_PLAN §4.2.

IMPORTANT frozen decisions:
  - ``actions`` is field-only and NOT in consistency scope (§4.8).
  - No TRANS ↔ FUNC trace direction exists (§4.8).
  - No TRANS ↔ IFACE trace direction exists (§4.6).
"""

from __future__ import annotations

from pydantic import Field

from .common import ArtifactBase, ArtifactType


class Transition(ArtifactBase):
    """
    State transition artifact for propulsion control logic.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.TRANSITION,
        description="Must be 'transition'",
    )
    name: str = Field(
        description="Human-readable transition name",
    )
    description: str = Field(
        default="",
        description="What this transition represents",
    )
    source_mode: str = Field(
        description="MODE-xxxx ID of the source mode",
    )
    target_mode: str = Field(
        description="MODE-xxxx ID of the target mode",
    )
    trigger_signal: str = Field(
        default="",
        description="Convenience label for the trigger signal (IFACE reference, field-only per §4.6)",
    )
    guard: str = Field(
        default="",
        description="GUARD-xxxx ID of the guard condition (empty = unconditional transition)",
    )
    priority: int = Field(
        default=100,
        ge=0,
        description="Arbitration priority (lower = higher priority, 0 = highest)",
    )
    actions: list[str] = Field(
        default_factory=list,
        description="FUNC-xxxx IDs of actions to execute on transition (field-only, NOT in consistency scope per §4.8)",
    )
    is_reversible: bool = Field(
        default=True,
        description="Whether the reverse transition exists or is expected",
    )

    # Cross-references
    related_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs related to this transition",
    )
    related_abnormals: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs that may trigger this transition",
    )
