"""
Common data model components shared across all artifact types.

This module defines the common metadata envelope, provenance model,
and base artifact class that all specific artifact types inherit from.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Strict ISO8601-ish regex to ensure standard dates without weird formats
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[\+\-][0-9]{2}:[0-9]{2})?)?$")



# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactType(str, Enum):
    """Valid artifact type identifiers."""
    REQUIREMENT = "requirement"
    FUNCTION = "function"
    INTERFACE = "interface"
    ABNORMAL = "abnormal"
    GLOSSARY_ENTRY = "glossary_entry"
    TRACE_LINK = "trace_link"
    # Phase 2A additions
    MODE = "mode"
    TRANSITION = "transition"
    GUARD = "guard"


class LifecycleStatus(str, Enum):
    """Artifact lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    WITHDRAWN = "withdrawn"


class ReviewStatus(str, Enum):
    """Review workflow status."""
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    FROZEN = "frozen"
    REJECTED = "rejected"


class ProvenanceSourceType(str, Enum):
    """How the artifact content was produced."""
    HUMAN_AUTHORED = "human_authored"
    AI_EXTRACTED = "ai_extracted"
    AI_INFERRED = "ai_inferred"
    MIXED = "mixed"
    REFERENCE = "reference"


class ConfidenceLevel(float, Enum):
    """Named confidence thresholds for reference (actual field is float)."""
    VERY_LOW = 0.1
    LOW = 0.3
    MODERATE = 0.5
    HIGH = 0.7
    VERY_HIGH = 0.9


# ---------------------------------------------------------------------------
# ID pattern
# ---------------------------------------------------------------------------

# Regex for valid artifact IDs: PREFIX-NNNN
ID_PATTERN = re.compile(r"^(REQ|FUNC|IFACE|ABN|TERM|TRACE|MODE|TRANS|GUARD)-[0-9]{4}$")

# Mapping from ID prefix to expected artifact_type
PREFIX_TO_TYPE: dict[str, ArtifactType] = {
    "REQ": ArtifactType.REQUIREMENT,
    "FUNC": ArtifactType.FUNCTION,
    "IFACE": ArtifactType.INTERFACE,
    "ABN": ArtifactType.ABNORMAL,
    "TERM": ArtifactType.GLOSSARY_ENTRY,
    "TRACE": ArtifactType.TRACE_LINK,
    # Phase 2A additions
    "MODE": ArtifactType.MODE,
    "TRANS": ArtifactType.TRANSITION,
    "GUARD": ArtifactType.GUARD,
}


def validate_artifact_id(artifact_id: str) -> str:
    """Validate that an artifact ID matches the required pattern."""
    if not ID_PATTERN.match(artifact_id):
        raise ValueError(
            f"Invalid artifact ID '{artifact_id}'. "
            f"Must match pattern PREFIX-NNNN where PREFIX is one of "
            f"REQ, FUNC, IFACE, ABN, TERM, TRACE, MODE, TRANS, GUARD "
            f"and NNNN is 4 digits."
        )
    return artifact_id


def get_id_prefix(artifact_id: str) -> str:
    """Extract the prefix from a valid artifact ID."""
    return artifact_id.split("-")[0]


# ---------------------------------------------------------------------------
# Provenance model
# ---------------------------------------------------------------------------

class Provenance(BaseModel):
    """
    Tracks how artifact content was produced and its review state.
    
    This is central to APLH's knowledge governance: every piece of content
    must declare its origin and confidence level so that reviewers can
    assess trustworthiness.
    """
    source_type: ProvenanceSourceType = Field(
        description="How this content was produced"
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="List of source document references (document IDs, URLs, etc.)"
    )
    method: str = Field(
        default="",
        description="Description of the production method (e.g., 'extracted by Gemini 3.1 Pro from CCAR-33 §33.28')"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence level 0.0–1.0"
    )
    reviewed_by: str = Field(
        default="",
        description="Reviewer identity (empty if not yet reviewed)"
    )
    review_date: str = Field(
        default="",
        pattern=r"^(|[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[\+\-][0-9]{2}:[0-9]{2})?)?)$",
        description="ISO date of review (empty if not yet reviewed)"
    )



# ---------------------------------------------------------------------------
# Base artifact model
# ---------------------------------------------------------------------------

class ArtifactBase(BaseModel):
    """
    Base model for all APLH artifacts.
    
    Provides the common metadata envelope that every artifact carries.
    Specific artifact types (Requirement, Function, etc.) extend this
    with their domain-specific fields.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(description="Unique artifact ID (e.g., REQ-0001)")

    artifact_type: ArtifactType = Field(description="Artifact type identifier")
    version: str = Field(
        default="0.1.0",
        description="Semantic version of this artifact"
    )
    status: LifecycleStatus = Field(
        default=LifecycleStatus.DRAFT,
        description="Lifecycle status"
    )
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(source_type=ProvenanceSourceType.HUMAN_AUTHORED),
        description="Content provenance and confidence metadata"
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.DRAFT,
        description="Review workflow status"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags for filtering/grouping"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[\+\-][0-9]{2}:[0-9]{2})?$",
        description="ISO 8601 creation timestamp"
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[\+\-][0-9]{2}:[0-9]{2})?$",
        description="ISO 8601 last-updated timestamp"
    )

    notes: str = Field(
        default="",
        description="Free-text notes, assumptions, open questions"
    )

    @field_validator("id")
    @classmethod
    def check_id_format(cls, v: str) -> str:
        return validate_artifact_id(v)
