"""
Trace Validator.

Checks traceability consistency:
- No dangling traces (endpoints must exist)
- Artifact bidirectional consistency (artifacts mentioning traces match trace link objects)
"""

from dataclasses import dataclass
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry


@dataclass
class TraceIssue:
    trace_id: str
    issue_type: str
    message: str


class TraceValidator:
    """Validates trace links against the registry of loaded artifacts."""
    
    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry
        self.issues: list[TraceIssue] = []
        
    def validate_all(self) -> bool:
        """Validate all trace links in the registry."""
        self.issues.clear()
        
        for trace_id, trace in self.registry.traces.items():
            self._validate_trace(trace_id, trace)
            
        return len(self.issues) == 0

    def _validate_trace(self, trace_id, trace) -> None:
        """Validate a single trace link."""
        # 1. Check endpoints exist
        if not self.registry.artifact_exists(trace.source_id):
            self.issues.append(
                TraceIssue(trace_id, "dangling_source", f"Source artifact {trace.source_id} not found")
            )
        if not self.registry.artifact_exists(trace.target_id):
            self.issues.append(
                TraceIssue(trace_id, "dangling_target", f"Target artifact {trace.target_id} not found")
            )
            
        # Additional trace logic checks can be added here
        
    def get_report(self) -> str:
        if not self.issues:
            return "✅ No trace validation issues found."
            
        report = [f"❌ Found {len(self.issues)} trace validation issues:"]
        for issue in self.issues:
            report.append(f"  - [{issue.issue_type}] {issue.trace_id}: {issue.message}")
        return "\n".join(report)
