"""
Artifact loader service.

Loads raw YAML files into validated Pydantic models.
"""

from pathlib import Path
from typing import Any

from aero_prop_logic_harness.models import (
    ArtifactBase,
    Requirement,
    Function,
    Interface,
    Abnormal,
    GlossaryEntry,
    TraceLink,
    Mode,
    Transition,
    Guard,
    PREFIX_TO_TYPE,
    ArtifactType,
    get_id_prefix,
)
from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
from aero_prop_logic_harness.path_constants import iter_artifact_yamls


def _get_model_class(artifact_type: str) -> type[ArtifactBase] | type[TraceLink]:
    """Get the Pydantic model class for an artifact type."""
    mapping = {
        ArtifactType.REQUIREMENT.value: Requirement,
        ArtifactType.FUNCTION.value: Function,
        ArtifactType.INTERFACE.value: Interface,
        ArtifactType.ABNORMAL.value: Abnormal,
        ArtifactType.GLOSSARY_ENTRY.value: GlossaryEntry,
        ArtifactType.TRACE_LINK.value: TraceLink,
        # Phase 2A additions
        ArtifactType.MODE.value: Mode,
        ArtifactType.TRANSITION.value: Transition,
        ArtifactType.GUARD.value: Guard,
    }
    if artifact_type not in mapping:
        raise ValueError(f"Unknown artifact type: {artifact_type}")
    return mapping[artifact_type]


def load_artifact(path: Path | str) -> ArtifactBase | TraceLink:
    """
    Load an artifact from a YAML file.
    
    Automatically determines the correct Pydantic model based on the
    'artifact_type' field in the YAML, or inferred from ID prefix.
    Validates the content against the model.
    Also strictly validates that the file matches ID_AND_NAMING_CONVENTIONS.
    """
    file_path = Path(path)
    data = load_yaml(file_path)
    
    if not isinstance(data, dict):
        raise ValueError(f"File {file_path} must contain a YAML dictionary.")
        
    if "id" not in data:
        raise ValueError(f"Artifact in {file_path} missing 'id' field.")
        
    artifact_id = data["id"]
    prefix = get_id_prefix(artifact_id)
    
    # Strict naming convention: file name must be exact match of id.lower() + .yaml
    expected_filename = f"{artifact_id.lower()}.yaml"
    if file_path.name != expected_filename:
        raise ValueError(f"File naming violation: Expected '{expected_filename}', got '{file_path.name}'")
        
    # Strict directory convention based on prefix
    PREFIX_TO_DIRECTORY = {
        "REQ": "requirements",
        "FUNC": "functions",
        "IFACE": "interfaces",
        "ABN": "abnormals",
        "TERM": "glossary",
        "TRACE": "trace",
        # Phase 2A additions
        "MODE": "modes",
        "TRANS": "transitions",
        "GUARD": "guards",
    }
    expected_dir = PREFIX_TO_DIRECTORY.get(prefix)
    if expected_dir and file_path.parent.name != expected_dir:
        raise ValueError(f"Directory naming violation: Artifact with prefix {prefix} must be placed in a '{expected_dir}' directory, got '{file_path.parent.name}'")


    if prefix not in PREFIX_TO_TYPE:
        raise ValueError(f"Unknown prefix '{prefix}' for ID '{artifact_id}' in {path}")
    expected_artifact_type = PREFIX_TO_TYPE[prefix].value
    
    artifact_type = data.get("artifact_type")
    if artifact_type and artifact_type != expected_artifact_type:
        raise ValueError(f"Type spoofing detected: ID '{artifact_id}' implies type '{expected_artifact_type}', but YAML metadata claims '{artifact_type}'")

    artifact_type = expected_artifact_type

        
    # Get model class and instantiate (which triggers Pydantic validation)
    model_cls = _get_model_class(artifact_type)
    return model_cls(**data)


def load_artifacts_from_dir(directory: Path | str) -> list[ArtifactBase | TraceLink]:
    """Load all valid artifacts from a directory tree.

    Uses the shared ``iter_artifact_yamls`` traversal so that every CLI
    command sees the identical set of artifact files.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return []

    artifacts = []
    for yaml_file in iter_artifact_yamls(dir_path):
        try:
            artifact = load_artifact(yaml_file)
            artifacts.append(artifact)
        except Exception as e:
            # Re-raise with file context
            raise RuntimeError(f"Failed to load artifact from {yaml_file}: {e}") from e

    return artifacts
