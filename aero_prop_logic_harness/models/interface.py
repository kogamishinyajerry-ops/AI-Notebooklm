"""
Interface data model.

An Interface represents a logical interface between components or subsystems
in the propulsion control system. It captures signal definitions, timing,
fault behavior, and relationships to requirements and functions.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import ArtifactBase, ArtifactType


class SignalDefinition(BaseModel):
    """A single signal within an interface."""
    name: str = Field(description="Signal name")
    direction: str = Field(
        default="",
        description="Signal direction: 'in', 'out', or 'bidirectional'"
    )
    data_type: str = Field(
        default="",
        description="Data type (e.g., 'float32', 'boolean', 'enum', 'integer')"
    )
    unit: str = Field(
        default="",
        description="Engineering unit (e.g., 'rpm', 'degC', '%', 'psi')"
    )
    valid_range: str = Field(
        default="",
        description="Valid range description (e.g., '0–120%', '−40–800 degC')"
    )
    description: str = Field(
        default="",
        description="Brief description of what this signal represents"
    )


class Interface(ArtifactBase):
    """
    Logical interface specification for propulsion control system.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.INTERFACE,
        description="Must be 'interface'"
    )
    name: str = Field(
        description="Interface name"
    )
    interface_type: str = Field(
        default="",
        description="Type of interface (e.g., 'data_bus', 'discrete', 'analog', 'software_api')"
    )
    producer: str = Field(
        default="",
        description="Component or subsystem that produces/sends data"
    )
    consumer: str = Field(
        default="",
        description="Component or subsystem that consumes/receives data"
    )
    signals: list[SignalDefinition] = Field(
        default_factory=list,
        description="Signal definitions within this interface"
    )
    timing_semantics: str = Field(
        default="",
        description="Timing behavior description (e.g., 'periodic', 'event-driven', 'on-change')"
    )
    update_rate: str = Field(
        default="",
        description="Update rate or frequency (e.g., '50 Hz', 'on-demand')"
    )
    fault_flags: list[str] = Field(
        default_factory=list,
        description="Fault/status flags associated with this interface"
    )
    degradation_behavior: str = Field(
        default="",
        description="What happens when this interface degrades or fails"
    )
    related_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs related to this interface"
    )
    related_functions: list[str] = Field(
        default_factory=list,
        description="FUNC-xxxx IDs related to this interface"
    )
    related_abnormals: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs related to this interface"
    )
    # Phase 2A additive fields (§2.6)
    related_modes: list[str] = Field(
        default_factory=list,
        description="MODE-xxxx IDs of modes that monitor this interface"
    )
    related_guards: list[str] = Field(
        default_factory=list,
        description="GUARD-xxxx IDs of guards that reference signals from this interface"
    )
