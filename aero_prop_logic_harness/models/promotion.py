"""
Promotion, readiness, and governance data models.

Provides Pydantic schemas for formal readiness assessment, promotion path,
and Phase 6 governance reports.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ReadinessPrerequisite(BaseModel):
    """A prerequisite check for baseline readiness."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Identifier for the prerequisite")
    name: str = Field(description="Name of the check")
    status: str = Field(description="Status of check: met | not_met | partial")
    detail: str = Field(description="Detailed result of the check")

class ReadinessBlocker(BaseModel):
    """A blocking issue preventing formal baseline freeze."""
    model_config = ConfigDict(extra="forbid")
    blocker_id: str = Field(description="Unique identifier for the blocker")
    severity: str = Field(description="Severity: critical | advisory")
    description: str = Field(description="Description of the blocking issue")
    resolution_path: str = Field(description="Suggested path to resolve the blocker")

class ReadinessReport(BaseModel):
    """Machine-readable assessment of formal baseline freeze readiness."""
    model_config = ConfigDict(extra="forbid")
    report_id: str = Field(description="Unique report ID")
    generated_at: str = Field(description="ISO 8601 timestamp")
    formal_baseline_dir: str = Field(description="Path to formal baseline")
    demo_baseline_dir: str = Field(description="Path to demo evidence baseline")
    prerequisites: List[ReadinessPrerequisite]
    blockers: List[ReadinessBlocker]
    overall_status: str = Field(description="not_ready | partially_ready | ready_for_review")
    met_count: int
    total_count: int

class PromotionBlocker(BaseModel):
    """A blocking issue preventing promotion of an artifact."""
    model_config = ConfigDict(extra="forbid")
    blocker_id: str = Field(description="Unique identifier for the blocker")
    candidate_id: str = Field(description="Related candidate ID")
    severity: str = Field(description="Severity: critical | advisory")
    check_name: str = Field(description="Name of the check that failed")
    description: str = Field(description="Description of the blocking issue")
    resolution: str = Field(description="Suggested action to resolve the blocker")

class PromotionCandidate(BaseModel):
    """Nomination of an artifact for promotion to formal baseline."""
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(description="Unique ID for candidate")
    artifact_type: str = Field(description="MODE | TRANSITION | GUARD")
    source_path: str = Field(description="Path in demo baseline")
    target_path: str = Field(description="Destination path in formal baseline")
    artifact_id: str = Field(description="Artifact ID (e.g. MODE-0001)")
    nominated_by: str = Field(description="Submitter name")
    nominated_at: str = Field(description="ISO 8601 timestamp")
    demo_evidence: Dict[str, Any] = Field(description="Evidence correlation data")
    validation_status: str = Field(description="pending | passed | failed")
    blockers: List[PromotionBlocker] = Field(default_factory=list)

class PromotionManifest(BaseModel):
    """Decision record for a batch of promotion candidates."""
    model_config = ConfigDict(extra="forbid")
    manifest_id: str = Field(description="Unique manifest ID")
    created_at: str = Field(description="ISO 8601 timestamp")
    created_by: str = Field(description="Creator name")
    formal_baseline_dir: str = Field(description="Formal baseline path")
    source_baseline_dir: str = Field(description="Source demo baseline path")
    candidates: List[Dict[str, str]] = Field(description="List of candidate summaries -> {'candidate_id': ..., 'status': ...}")
    overall_status: str = Field(description="ready | partial | blocked")
    promotion_decision: str = Field(description="pending_review | approved | rejected")
    decision_by: Optional[str] = Field(default=None, description="Reviewer name")
    decision_at: Optional[str] = Field(default=None, description="Decision timestamp")
    lifecycle_status: str = Field(default="pending", description="pending | promoted | expired")

class PromotionPlan(BaseModel):
    """Specific physical file copy plan derived from a ready manifest."""
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    operations: List[Dict[str, str]] = Field(description="List of {source: ..., target: ...}")

class PromotionResult(BaseModel):
    """Result of a promotion execution."""
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    success: bool
    promoted_files: List[str]
    failed_files: List[str]
    error_message: Optional[str] = None

class PromotionAuditRecord(BaseModel):
    """Ledger entry for a physical promotion."""
    model_config = ConfigDict(extra="forbid")
    timestamp: str = Field(description="ISO 8601 timestamp")
    manifest_id: str
    executor: str
    files_promoted: int
    files_failed: int
    status: str = Field(description="success | partial_failure | failure")

class FormalPopulationReport(BaseModel):
    """Post-promotion integrity check result for formal baseline."""
    model_config = ConfigDict(extra="forbid")
    manifest_id: str = Field(description="Manifest ID that triggered this check")
    schema_validation: str = Field(description="pass | fail")
    trace_consistency: str = Field(description="pass | fail")
    mode_validator: str = Field(description="pass | fail | not_applicable")
    coverage_validator: str = Field(description="pass | fail | not_applicable")
    overall_pass: bool = Field(description="True if all validators pass (not_applicable counts as pass)")


class GateResult(BaseModel):
    """Machine-readable result for a single Phase 6 gate."""
    model_config = ConfigDict(extra="forbid")
    gate_id: str = Field(description="Gate identifier, e.g. G6-A")
    tier: str = Field(description="Gate tier: T1 | T2 | T3")
    passed: bool = Field(description="Whether the gate currently passes")
    detail: str = Field(description="Human-readable gate summary")


class AdvisoryResolution(BaseModel):
    """Formal routing and closure record for a Phase 6 advisory item."""
    model_config = ConfigDict(extra="forbid")
    advisory_id: str
    title: str
    phase6_subphase: str
    priority: str
    gate_id: str
    tier: str
    status: str = Field(description="open | implemented | closed")
    resolution_rule: str
    evidence_refs: List[str] = Field(default_factory=list)
    notes: str = ""


class AcceptanceAuditEntry(BaseModel):
    """Governance log entry for review intake and handoff milestones."""
    model_config = ConfigDict(extra="forbid")
    timestamp: str
    actor: str
    action: str
    state_before: str
    state_after: str
    evidence_refs: List[str] = Field(default_factory=list)
    notes: str = ""


class FreezeReadinessReport(BaseModel):
    """Phase 6 machine-readable review packet summary."""
    model_config = ConfigDict(extra="forbid")
    report_id: str
    generated_at: str
    formal_baseline_dir: str
    source_demo_dir: str
    formal_state: str = Field(
        description="Current highest classified state: unpopulated | promoted | populated | post-validated | ready_for_freeze_review | accepted_for_review | pending_manual_decision"
    )
    population_state: str = Field(description="unpopulated | promoted | populated")
    validation_state: str = Field(description="not_validated | validation_failed | post-validated")
    review_preparation_state: str = Field(description="not_ready | ready_for_freeze_review")
    gate_results: List[GateResult] = Field(default_factory=list)
    blocking_conditions: List[str] = Field(default_factory=list)
    advisory_status_refs: List[str] = Field(default_factory=list)
    manifest_refs: List[str] = Field(default_factory=list)
    promotion_audit_refs: List[str] = Field(default_factory=list)
    manual_actions_required: List[str] = Field(default_factory=list)


class FormalPopulationInventoryItem(BaseModel):
    """A deterministic source-to-formal artifact copy candidate for Phase 7."""
    model_config = ConfigDict(extra="forbid")
    artifact_plane: str = Field(description="supporting | phase2a")
    source_dir: str = Field(description="Allowlisted source directory name")
    source_path: str = Field(description="Absolute source artifact path")
    target_path: str = Field(description="Logical target path under artifacts/")
    artifact_id: str = Field(description="Artifact ID inferred from file name")


class FormalPopulationApproval(BaseModel):
    """Reviewed evidence intake record required before Phase 7 population."""
    model_config = ConfigDict(extra="forbid")
    approval_id: str
    approved_by: str
    approved_at: str
    decision: str = Field(description="approved")
    source_baseline_dir: str
    formal_baseline_dir: str
    allowed_source_dirs: List[str]
    expected_file_count: int
    evidence_refs: List[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("approved_by", "approval_id")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be non-blank")
        return value

    @field_validator("decision")
    @classmethod
    def _approved_only(cls, value: str) -> str:
        if value != "approved":
            raise ValueError("formal population approval decision must be 'approved'")
        return value


class FormalPopulationAuditRecord(BaseModel):
    """Governance audit record for Phase 7 full formal source population."""
    model_config = ConfigDict(extra="forbid")
    timestamp: str
    approval_id: str
    promotion_manifest_id: str
    executor: str
    files_populated: int
    support_files_populated: int
    phase2_files_populated: int
    status: str
    target_paths: List[str] = Field(default_factory=list)


class FormalPopulationResult(BaseModel):
    """Result of a Phase 7 controlled formal population attempt."""
    model_config = ConfigDict(extra="forbid")
    success: bool
    approval_id: str
    promotion_manifest_id: str
    files_populated: List[str] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    readiness_state: Optional[str] = None
