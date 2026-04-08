"""
Consistency Validator.

Performs domain-level cross checks on artifacts:
- Embedded links (e.g., req.linked_functions) must point to existing artifacts
- Confidence vs Provenance rule checks
- Review status rule checks
"""

from dataclasses import dataclass

from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.models import (
    Requirement, Function, Interface, Abnormal,
    Mode, Transition, Guard,
    ProvenanceSourceType, ReviewStatus
)


@dataclass
class ConsistencyIssue:
    artifact_id: str
    issue_type: str
    message: str


class ConsistencyValidator:
    """Validates cross-artifact consistency and business rules."""
    
    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry
        self.issues: list[ConsistencyIssue] = []
        
    def validate_all(self) -> bool:
        self.issues.clear()
        
        for art_id, artifact in self.registry.artifacts.items():
            self._validate_embedded_links(art_id, artifact)
            self._validate_governance_rules(art_id, artifact)
            
        self._validate_trace_reverse_loop()
            
        return len(self.issues) == 0

    def _get_all_embedded_links(self, artifact) -> list[str]:
        """Extract all cross-reference IDs that participate in consistency scope.

        IMPORTANT frozen decisions (§4.8):
          - Transition.actions is field-only → NOT extracted
          - Function.related_transitions is field-only → NOT extracted
        """
        links = []
        if isinstance(artifact, Requirement):
            links.extend(artifact.linked_functions)
            links.extend(artifact.linked_interfaces)
            links.extend(artifact.linked_abnormals)
            # Phase 2A additive fields (§2.6)
            links.extend(artifact.linked_modes)
            links.extend(artifact.linked_transitions)
            links.extend(artifact.linked_guards)
        elif isinstance(artifact, Function):
            links.extend(artifact.dependent_requirements)
            links.extend(artifact.related_interfaces)
            links.extend(artifact.abnormal_considerations)
            # Phase 2A additive field (§2.6)
            links.extend(artifact.related_modes)
            # NOTE: artifact.related_transitions NOT extracted — §4.8 frozen decision
        elif isinstance(artifact, Interface):
            links.extend(artifact.related_requirements)
            links.extend(getattr(artifact, 'related_functions', []))
            links.extend(getattr(artifact, 'related_abnormals', []))
            # Phase 2A additive fields (§2.6)
            links.extend(artifact.related_modes)
            links.extend(artifact.related_guards)
        elif isinstance(artifact, Abnormal):
            links.extend(artifact.related_requirements)
            links.extend(artifact.related_functions)
            links.extend(artifact.related_interfaces)
            # Phase 2A additive fields (§2.6)
            links.extend(artifact.related_modes)
            links.extend(artifact.related_transitions)
        elif isinstance(artifact, Mode):
            links.extend(artifact.active_functions)          # (MODE, FUNC, activates) source
            links.extend(artifact.monitored_interfaces)      # (MODE, IFACE, monitors) source
            links.extend(artifact.related_requirements)      # (REQ, MODE, requires_mode) target
            links.extend(artifact.related_abnormals)         # (ABN, MODE, triggers_mode) target
            links.extend(artifact.incoming_transitions)      # (TRANS, MODE, enters) target §2.7
            links.extend(artifact.outgoing_transitions)      # (TRANS, MODE, exits) target §2.7
        elif isinstance(artifact, Transition):
            links.append(artifact.source_mode)               # (TRANS, MODE, exits) source
            links.append(artifact.target_mode)               # (TRANS, MODE, enters) source
            if artifact.guard:
                links.append(artifact.guard)                 # (TRANS, GUARD, guarded_by) source
            links.extend(artifact.related_requirements)      # (REQ, TRANS, requires_transition) target
            links.extend(artifact.related_abnormals)         # (ABN, TRANS, triggers_transition) target
            # NOTE: artifact.actions NOT extracted — §4.8 frozen decision
        elif isinstance(artifact, Guard):
            links.extend(artifact.related_interfaces)        # (GUARD, IFACE, observes) source
            links.extend(artifact.related_requirements)      # (REQ, GUARD, defines_condition) target
            links.extend(artifact.used_by_transitions)       # (TRANS, GUARD, guarded_by) target §2.7
        return links

    def _validate_embedded_links(self, art_id: str, artifact) -> None:
        """Check all 'linked_X' fields to ensure references point to existing artifacts AND
        have a matching explicit TraceLink."""

        links_to_check = self._get_all_embedded_links(artifact)

        for target_id in links_to_check:
            if not self.registry.artifact_exists(target_id):
                self.issues.append(
                    ConsistencyIssue(
                        art_id, "dangling_embedded_link",
                        f"Embedded link points to non-existent artifact: {target_id}"
                    )
                )
            else:
                # Check that a trace link exists in either direction
                traces_out = self.registry.outgoing_traces.get(art_id, [])
                traces_in = self.registry.incoming_traces.get(art_id, [])
                
                has_trace = False
                for t in traces_out:
                    if t.target_id == target_id:
                        has_trace = True
                for t in traces_in:
                    if t.source_id == target_id:
                        has_trace = True
                        
                if not has_trace:
                    self.issues.append(
                        ConsistencyIssue(
                            art_id, "missing_trace_link",
                            f"Embedded link to {target_id} lacks an explicit TraceLink counterpart"
                        )
                    )

    def _validate_trace_reverse_loop(self) -> None:
        """Ensure all TraceLinks are acknowledged by both endpoints in their embedded references."""
        for trace_id, trace in self.registry.traces.items():
            src_id = trace.source_id
            tgt_id = trace.target_id
            
            src_art = self.registry.artifacts.get(src_id)
            tgt_art = self.registry.artifacts.get(tgt_id)
            
            if src_art and tgt_id not in self._get_all_embedded_links(src_art):
                self.issues.append(
                    ConsistencyIssue(
                        trace.id, "unacknowledged_trace_source",
                        f"TraceLink {trace.id} exists, but source {src_id} does not claim target {tgt_id}"
                    )
                )
            
            if tgt_art and src_id not in self._get_all_embedded_links(tgt_art):
                self.issues.append(
                    ConsistencyIssue(
                        trace.id, "unacknowledged_trace_target",
                        f"TraceLink {trace.id} exists, but target {tgt_id} does not claim source {src_id}"
                    )
                )


    def _validate_governance_rules(self, art_id: str, artifact) -> None:
        """Check boundary rules for AI, confidence, and review status."""
        prov = artifact.provenance
        
        # Rule: AI extracted/inferred cannot be frozen without high confidence
        is_ai = prov.source_type in (
            ProvenanceSourceType.AI_EXTRACTED,
            ProvenanceSourceType.AI_INFERRED
        )
        if is_ai and artifact.review_status == ReviewStatus.FROZEN:
            if prov.confidence < 0.5:
                self.issues.append(
                    ConsistencyIssue(
                        art_id, "invalid_freeze",
                        "Artifact is FROZEN but AI confidence is < 0.5"
                    )
                )
                
        # Rule: If reviewed or frozen, reviewer info should usually be present
        if artifact.review_status in (ReviewStatus.REVIEWED, ReviewStatus.FROZEN):
            if not prov.reviewed_by:
                self.issues.append(
                    ConsistencyIssue(
                        art_id, "missing_reviewer",
                        f"Artifact is {artifact.review_status.name} but missing reviewed_by"
                    )
                )


    def get_report(self) -> str:
        if not self.issues:
            return "✅ No consistency issues found."
            
        report = [f"❌ Found {len(self.issues)} consistency issues:"]
        for issue in self.issues:
            report.append(f"  - [{issue.issue_type}] {issue.artifact_id}: {issue.message}")
        return "\n".join(report)
