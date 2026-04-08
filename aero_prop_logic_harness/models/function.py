"""
Function data model.

A Function represents a logical function within the propulsion control system.
It describes what the function does, its inputs/outputs, preconditions,
postconditions, and relationships to requirements and interfaces.
"""

from __future__ import annotations

from pydantic import Field

from .common import ArtifactBase, ArtifactType


class Function(ArtifactBase):
    """
    Functional decomposition entry for propulsion control logic.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.FUNCTION,
        description="Must be 'function'"
    )
    name: str = Field(
        description="Function name (concise, verb-noun style preferred)"
    )
    purpose: str = Field(
        description="What this function accomplishes in the control system"
    )
    inputs: list[str] = Field(
        default_factory=list,
        description="Input signals, parameters, or data consumed by this function"
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Output signals, commands, or data produced by this function"
    )
    preconditions: list[str] = Field(
        default_factory=list,
        description="Conditions that must be true before this function executes"
    )
    postconditions: list[str] = Field(
        default_factory=list,
        description="Conditions guaranteed after successful function execution"
    )
    dependent_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs that this function implements or satisfies"
    )
    related_interfaces: list[str] = Field(
        default_factory=list,
        description="IFACE-xxxx IDs of interfaces this function uses or provides"
    )
    abnormal_considerations: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs of abnormal conditions this function must handle"
    )
    owner_domain: str = Field(
        default="",
        description="Engineering domain that owns this function (e.g., 'fuel_control', 'thrust_management')"
    )
    # Phase 2A additive fields (§2.6)
    related_modes: list[str] = Field(
        default_factory=list,
        description="MODE-xxxx IDs of modes this function is active in"
    )
    related_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs of transitions that invoke this function as an action"
    )
