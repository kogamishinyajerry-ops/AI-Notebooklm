"""
Requirement data model.

A Requirement represents a structured engineering requirement statement
for propulsion system control logic. It captures what the system must do,
under what conditions, and how compliance can be observed.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import ArtifactBase, ArtifactType


class Requirement(ArtifactBase):
    """
    Structured engineering requirement for propulsion control logic.
    
    Fields capture the requirement statement, its conditions, expected system
    response, verification approach, and links to related artifacts.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.REQUIREMENT,
        description="Must be 'requirement'"
    )
    title: str = Field(
        description="Short descriptive title of the requirement"
    )
    description: str = Field(
        description="Full requirement statement in engineering prose"
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="Source documents this requirement derives from (e.g., regulation clause, spec section)"
    )
    category: str = Field(
        default="",
        description="Requirement category (e.g., 'thrust_control', 'engine_protection', 'bleed_control', 'monitoring')"
    )
    lifecycle_phase: str = Field(
        default="",
        description="Applicable lifecycle phase (e.g., 'ground_start', 'takeoff', 'cruise', 'shutdown', 'all')"
    )
    triggers: list[str] = Field(
        default_factory=list,
        description="Events or conditions that activate this requirement"
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Preconditions that must be true for this requirement to apply"
    )
    expected_response: str = Field(
        default="",
        description="What the system should do when triggered under the stated conditions"
    )
    verification_observables: list[str] = Field(
        default_factory=list,
        description="Observable outputs or states that can verify compliance"
    )
    safety_relevance: bool = Field(
        default=False,
        description="Whether this requirement has safety implications (triggers additional review)"
    )
    linked_functions: list[str] = Field(
        default_factory=list,
        description="FUNC-xxxx IDs of functions that implement this requirement"
    )
    linked_interfaces: list[str] = Field(
        default_factory=list,
        description="IFACE-xxxx IDs of interfaces related to this requirement"
    )
    linked_abnormals: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs of abnormal conditions related to this requirement"
    )
    # Phase 2A additive fields (§2.6)
    linked_modes: list[str] = Field(
        default_factory=list,
        description="MODE-xxxx IDs of modes related to this requirement"
    )
    linked_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs of transitions related to this requirement"
    )
    linked_guards: list[str] = Field(
        default_factory=list,
        description="GUARD-xxxx IDs of guard conditions related to this requirement"
    )
