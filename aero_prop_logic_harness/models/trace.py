"""
Trace link data model.

A TraceLink represents a directed traceability relationship between two
APLH artifacts. The traceability skeleton enables impact analysis,
completeness checking, and review evidence generation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import ID_PATTERN, validate_artifact_id, ReviewStatus



class TraceLinkType(str, Enum):
    """Valid relationship types between artifacts."""
    IMPLEMENTS = "implements"          # FUNC implements REQ
    SATISFIES = "satisfies"            # FUNC/IFACE satisfies REQ
    USES = "uses"                      # FUNC uses IFACE
    DETECTS = "detects"                # FUNC detects ABN
    MITIGATES = "mitigates"            # FUNC mitigates ABN
    TRIGGERS = "triggers"              # ABN triggers FUNC
    AFFECTS = "affects"                # ABN affects IFACE
    CONSTRAINS = "constrains"          # REQ constrains IFACE
    RELATES_TO = "relates_to"          # General relationship
    # Phase 2A additions
    REQUIRES_MODE = "requires_mode"            # REQ requires MODE
    REQUIRES_TRANSITION = "requires_transition"  # REQ requires TRANS
    DEFINES_CONDITION = "defines_condition"     # REQ defines GUARD
    TRIGGERS_MODE = "triggers_mode"            # ABN triggers MODE
    TRIGGERS_TRANSITION = "triggers_transition"  # ABN triggers TRANS
    ACTIVATES = "activates"                    # MODE activates FUNC
    MONITORS = "monitors"                      # MODE monitors IFACE
    EXITS = "exits"                            # TRANS exits MODE (source)
    ENTERS = "enters"                          # TRANS enters MODE (target)
    GUARDED_BY = "guarded_by"                  # TRANS guarded by GUARD
    OBSERVES = "observes"                      # GUARD observes IFACE


# Valid (source_prefix, target_prefix, link_type) combinations
VALID_TRACE_DIRECTIONS: set[tuple[str, str, TraceLinkType]] = {
    # ── P0/P1 directions (14) ─────────────────────────────────────────
    ("REQ", "FUNC", TraceLinkType.IMPLEMENTS),
    ("REQ", "IFACE", TraceLinkType.CONSTRAINS),
    ("REQ", "IFACE", TraceLinkType.RELATES_TO),
    ("REQ", "ABN", TraceLinkType.RELATES_TO),
    ("FUNC", "REQ", TraceLinkType.SATISFIES),
    ("IFACE", "REQ", TraceLinkType.SATISFIES),
    ("FUNC", "IFACE", TraceLinkType.USES),
    ("FUNC", "ABN", TraceLinkType.RELATES_TO),
    ("FUNC", "ABN", TraceLinkType.DETECTS),
    ("FUNC", "ABN", TraceLinkType.MITIGATES),
    ("ABN", "FUNC", TraceLinkType.TRIGGERS),
    ("ABN", "FUNC", TraceLinkType.RELATES_TO),
    ("ABN", "IFACE", TraceLinkType.AFFECTS),
    ("ABN", "IFACE", TraceLinkType.RELATES_TO),
    # ── Phase 2A directions (11) ─────────────────────────────────────
    ("REQ", "MODE", TraceLinkType.REQUIRES_MODE),
    ("REQ", "TRANS", TraceLinkType.REQUIRES_TRANSITION),
    ("REQ", "GUARD", TraceLinkType.DEFINES_CONDITION),
    ("ABN", "MODE", TraceLinkType.TRIGGERS_MODE),
    ("ABN", "TRANS", TraceLinkType.TRIGGERS_TRANSITION),
    ("MODE", "FUNC", TraceLinkType.ACTIVATES),
    ("MODE", "IFACE", TraceLinkType.MONITORS),
    ("TRANS", "MODE", TraceLinkType.EXITS),
    ("TRANS", "MODE", TraceLinkType.ENTERS),
    ("TRANS", "GUARD", TraceLinkType.GUARDED_BY),
    ("GUARD", "IFACE", TraceLinkType.OBSERVES),
    # NOTE: No (TRANS, FUNC, ...) — §4.8 frozen decision (field-only)
    # NOTE: No (TRANS, IFACE, ...) — §4.6 frozen decision (field-only)
}



class TraceLink(BaseModel):
    """
    Directed traceability link between two APLH artifacts.
    
    Unlike other artifact types, TraceLink does not extend ArtifactBase
    because it is a relationship, not a standalone engineering artifact.
    It has its own lightweight metadata structure.
    """
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(description="Trace link ID (TRACE-xxxx)")

    source_id: str = Field(description="Source artifact ID")
    target_id: str = Field(description="Target artifact ID")
    link_type: TraceLinkType = Field(description="Relationship type")
    rationale: str = Field(
        default="",
        description="Why this trace link exists"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in this trace link (0.0–1.0)"
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.DRAFT,
        description="Review status: draft | reviewed | frozen"
    )
    created_at: str = Field(
        default="",
        pattern=r"^(|[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[\+\-][0-9]{2}:[0-9]{2})?)$",
        description="ISO 8601 creation timestamp"
    )

    notes: str = Field(
        default="",
        description="Additional notes"
    )

    @field_validator("id")
    @classmethod
    def check_trace_id(cls, v: str) -> str:
        validate_artifact_id(v)
        if not v.startswith("TRACE-"):
            raise ValueError(f"Trace link ID must start with 'TRACE-', got '{v}'")
        return v

    @field_validator("source_id", "target_id")
    @classmethod
    def check_endpoint_id(cls, v: str) -> str:
        return validate_artifact_id(v)

    @model_validator(mode="after")
    def check_direction(self) -> "TraceLink":
        """Validate that the source→target direction and link_type are allowed."""
        src_prefix = self.source_id.split("-")[0]
        tgt_prefix = self.target_id.split("-")[0]
        direction = (src_prefix, tgt_prefix, self.link_type)
        if direction not in VALID_TRACE_DIRECTIONS:
            raise ValueError(
                f"Invalid trace semantic: {src_prefix} -[{self.link_type.value}]-> {tgt_prefix}."
            )
        return self

