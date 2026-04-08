"""
Artifact Registry service.

Central repository of all loaded artifacts, providing fast lookups
and cross-referencing capabilities for validation.
"""

from collections import defaultdict
from pathlib import Path

from aero_prop_logic_harness.loaders.artifact_loader import load_artifacts_from_dir
from aero_prop_logic_harness.models import (
    ArtifactBase,
    TraceLink,
    get_id_prefix,
    ArtifactType,
)


class ArtifactRegistry:
    """Registry holding all artifacts loaded from the filesystem."""
    
    def __init__(self):
        # Maps artifact ID -> Artifact instance
        self.artifacts: dict[str, ArtifactBase] = {}
        # Maps trace ID -> TraceLink instance
        self.traces: dict[str, TraceLink] = {}
        
        # Indexes
        self.by_type: dict[str, list[ArtifactBase]] = defaultdict(list)
        
        # Trace indices
        self.outgoing_traces: dict[str, list[TraceLink]] = defaultdict(list)
        self.incoming_traces: dict[str, list[TraceLink]] = defaultdict(list)

    def load_from_directory(self, root_dir: Path | str) -> None:
        """Load all artifacts from the given root directory."""
        items = load_artifacts_from_dir(root_dir)
        for item in items:
            self._add_item(item)

    def _add_item(self, item: ArtifactBase | TraceLink) -> None:
        """Add an item to the registry and update indexes."""
        if isinstance(item, TraceLink):
            if item.id in self.traces:
                raise ValueError(f"Duplicate trace ID found: {item.id}")
            self.traces[item.id] = item
            self.outgoing_traces[item.source_id].append(item)
            self.incoming_traces[item.target_id].append(item)
        else:
            if item.id in self.artifacts:
                raise ValueError(f"Duplicate artifact ID found: {item.id}")
            self.artifacts[item.id] = item
            self.by_type[item.artifact_type.value].append(item)

    def get_artifact(self, artifact_id: str) -> ArtifactBase | None:
        """Get an artifact by ID."""
        return self.artifacts.get(artifact_id)
        
    def get_trace(self, trace_id: str) -> TraceLink | None:
        """Get a trace link by ID."""
        return self.traces.get(trace_id)

    def artifact_exists(self, artifact_id: str) -> bool:
        """Check if an artifact exists in the registry."""
        return artifact_id in self.artifacts

    def is_orphan(self, artifact_id: str) -> bool:
        """Check if an artifact is completely isolated (no incoming or outgoing traces)."""
        if artifact_id not in self.artifacts:
            return False # Not an artifact we know about
            
        # Glossary entries are inherently isolated
        if self.artifacts[artifact_id].artifact_type.value == "glossary_entry":
            return False
        
        has_outgoing = len(self.outgoing_traces.get(artifact_id, [])) > 0

        has_incoming = len(self.incoming_traces.get(artifact_id, [])) > 0
        return not (has_outgoing or has_incoming)
