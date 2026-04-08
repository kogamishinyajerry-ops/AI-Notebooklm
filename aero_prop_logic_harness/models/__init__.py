"""Models package — Pydantic data models for all APLH artifact types."""

from .common import (
    ArtifactBase,
    ArtifactType,
    ConfidenceLevel,
    ID_PATTERN,
    LifecycleStatus,
    PREFIX_TO_TYPE,
    Provenance,
    ProvenanceSourceType,
    ReviewStatus,
    get_id_prefix,
    validate_artifact_id,
)
from .requirement import Requirement
from .function import Function
from .interface import Interface
from .abnormal import Abnormal
from .glossary import GlossaryEntry
from .trace import TraceLink, TraceLinkType
from .freeze_status import FreezeGateStatus
# Phase 4 additions
from .promotion import (
    ReadinessReport,
    ReadinessPrerequisite,
    ReadinessBlocker,
    PromotionCandidate,
    PromotionBlocker,
    PromotionManifest,
    PromotionPlan,
    PromotionResult,
    PromotionAuditRecord,
    FormalPopulationReport,
    GateResult,
    AdvisoryResolution,
    AcceptanceAuditEntry,
    FreezeReadinessReport,
    FormalPopulationInventoryItem,
    FormalPopulationApproval,
    FormalPopulationAuditRecord,
    FormalPopulationResult,
)
# Phase 3 additions
from .signoff import SignoffEntry
# Phase 2A additions
from .mode import Mode
from .transition import Transition
from .guard import Guard, InputSignalRef
from .predicate import (
    AtomicPredicate,
    CompoundPredicate,
    PredicateCombinator,
    PredicateOperator,
    PredicateExpression,
)

__all__ = [
    "ArtifactBase",
    "ArtifactType",
    "ConfidenceLevel",
    "ID_PATTERN",
    "LifecycleStatus",
    "PREFIX_TO_TYPE",
    "Provenance",
    "ProvenanceSourceType",
    "ReviewStatus",
    "get_id_prefix",
    "validate_artifact_id",
    "Requirement",
    "Function",
    "Interface",
    "Abnormal",
    "GlossaryEntry",
    "TraceLink",
    "TraceLinkType",
    "FreezeGateStatus",
    # Phase 4 additions
    "ReadinessReport",
    "ReadinessPrerequisite",
    "ReadinessBlocker",
    "PromotionCandidate",
    "PromotionBlocker",
    "PromotionManifest",
    "PromotionPlan",
    "PromotionResult",
    "PromotionAuditRecord",
    "FormalPopulationReport",
    "GateResult",
    "AdvisoryResolution",
    "AcceptanceAuditEntry",
    "FreezeReadinessReport",
    "FormalPopulationInventoryItem",
    "FormalPopulationApproval",
    "FormalPopulationAuditRecord",
    "FormalPopulationResult",
    # Phase 3 additions
    "SignoffEntry",
    # Phase 2A additions
    "Mode",
    "Transition",
    "Guard",
    "InputSignalRef",
    "AtomicPredicate",
    "CompoundPredicate",
    "PredicateCombinator",
    "PredicateOperator",
    "PredicateExpression",
]
