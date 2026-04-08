"""
Abnormal data model.

An Abnormal represents an abnormal or failure condition that the propulsion
control system must detect, manage, and/or recover from. It captures detection
logic, effects, mitigations, and recovery conditions.
"""

from __future__ import annotations

from pydantic import Field

from .common import ArtifactBase, ArtifactType


class Abnormal(ArtifactBase):
    """
    Abnormal/failure condition description for propulsion control logic.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.ABNORMAL,
        description="Must be 'abnormal'"
    )
    name: str = Field(
        description="Abnormal condition name"
    )
    abnormal_type: str = Field(
        default="",
        description="Type classification (e.g., 'sensor_failure', 'actuator_failure', 'logic_fault', 'external_event')"
    )
    detection_logic: str = Field(
        default="",
        description="How this abnormal condition is detected (logic description, not code)"
    )
    entry_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions under which this abnormal is declared active"
    )
    system_effect: str = Field(
        default="",
        description="Effect on the propulsion system if this abnormal occurs"
    )
    crew_effect: str = Field(
        default="",
        description="Effect visible to the flight crew (alerts, annunciations, performance changes)"
    )
    maintenance_effect: str = Field(
        default="",
        description="Maintenance implications (dispatch restrictions, inspection requirements)"
    )
    mitigation: str = Field(
        default="",
        description="System-level mitigation or protective action"
    )
    fallback_mode: str = Field(
        default="",
        description="Degraded operating mode entered upon detection"
    )
    recovery_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions under which the system can exit this abnormal state"
    )
    related_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs related to this abnormal condition"
    )
    related_functions: list[str] = Field(
        default_factory=list,
        description="FUNC-xxxx IDs of functions involved in handling this abnormal"
    )
    related_interfaces: list[str] = Field(
        default_factory=list,
        description="IFACE-xxxx IDs of interfaces affected by this abnormal"
    )
    severity_hint: str = Field(
        default="",
        description="Severity guidance (e.g., 'minor', 'major', 'hazardous', 'catastrophic'). "
                    "Note: This is a working classification, not a formal safety assessment."
    )
    # Phase 2A additive fields (§2.6)
    related_modes: list[str] = Field(
        default_factory=list,
        description="MODE-xxxx IDs of modes affected by this abnormal condition"
    )
    related_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs of transitions triggered by this abnormal condition"
    )
