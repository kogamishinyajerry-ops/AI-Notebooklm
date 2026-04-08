"""
Mode data model (Phase 2A).

A Mode represents an operating mode of the propulsion control system
(e.g., Normal, Degraded, Emergency, Startup, Shutdown).  Modes form
a hierarchy through ``parent_mode`` and connect to transitions via
reciprocal fields ``incoming_transitions`` / ``outgoing_transitions``.

Per PHASE2_ARCHITECTURE_PLAN §4.1.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from .common import ArtifactBase, ArtifactType


# Allowed mode_type values per §4.1
_VALID_MODE_TYPES = frozenset({
    "normal",
    "degraded",
    "emergency",
    "startup",
    "shutdown",
    "test",
})


class Mode(ArtifactBase):
    """
    Operating mode artifact for propulsion control logic.
    """
    artifact_type: ArtifactType = Field(
        default=ArtifactType.MODE,
        description="Must be 'mode'",
    )
    name: str = Field(
        description="Human-readable mode name",
    )
    description: str = Field(
        default="",
        description="What this mode represents and when it is active",
    )
    mode_type: str = Field(
        description="Mode classification: normal | degraded | emergency | startup | shutdown | test",
    )
    parent_mode: str = Field(
        default="",
        description="MODE-xxxx ID of the parent mode (empty = top-level)",
    )
    is_initial: bool = Field(
        default=False,
        description="Whether this mode is the initial/default mode at power-on",
    )

    # Condition summaries (human-readable, NOT machine-checked per §4.7)
    entry_conditions: list[str] = Field(
        default_factory=list,
        description="Human-readable summary of conditions that cause entry into this mode",
    )
    exit_conditions: list[str] = Field(
        default_factory=list,
        description="Human-readable summary of conditions that cause exit from this mode",
    )

    # Cross-references to P0/P1 artifacts
    active_functions: list[str] = Field(
        default_factory=list,
        description="FUNC-xxxx IDs of functions active in this mode",
    )
    monitored_interfaces: list[str] = Field(
        default_factory=list,
        description="IFACE-xxxx IDs of interfaces monitored in this mode",
    )
    related_requirements: list[str] = Field(
        default_factory=list,
        description="REQ-xxxx IDs related to this mode",
    )
    related_abnormals: list[str] = Field(
        default_factory=list,
        description="ABN-xxxx IDs that may trigger entry/exit of this mode",
    )

    # §2.7 reciprocal fields
    incoming_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs of transitions whose target_mode is this mode",
    )
    outgoing_transitions: list[str] = Field(
        default_factory=list,
        description="TRANS-xxxx IDs of transitions whose source_mode is this mode",
    )

    @field_validator("mode_type")
    @classmethod
    def check_mode_type(cls, v: str) -> str:
        if v not in _VALID_MODE_TYPES:
            raise ValueError(
                f"Invalid mode_type '{v}'. "
                f"Must be one of: {', '.join(sorted(_VALID_MODE_TYPES))}"
            )
        return v
