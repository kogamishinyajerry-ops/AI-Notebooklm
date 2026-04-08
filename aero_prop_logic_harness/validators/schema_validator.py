"""
Schema Validator.

Validates artifacts against JSON schemas. Note: Since Pydantic models are used
for loading, much of the structural schema validation happens implicitly during
load. This validator wraps that process and provides reportable errors.
"""

from pathlib import Path
from dataclasses import dataclass

from aero_prop_logic_harness.loaders.artifact_loader import load_artifact
from aero_prop_logic_harness.path_constants import iter_artifact_yamls


@dataclass
class ValidationIssue:
    file_path: str
    issue_type: str  # e.g., 'schema_error', 'id_format', 'missing_field'
    message: str


class SchemaValidator:
    """Validates raw YAML files against Pydantic definitions."""
    
    def __init__(self):
        self.issues: list[ValidationIssue] = []
        
    def validate_file(self, file_path: Path | str) -> bool:
        """Validate a single file. Returns True if valid."""
        path = Path(file_path)
        if not path.is_file():
            self.issues.append(
                ValidationIssue(str(path), "file_not_found", "File does not exist")
            )
            return False
            
        try:
            # Pydantic validation happens upon initialization in load_artifact
            load_artifact(path)
            return True
        except Exception as e:
            self.issues.append(
                ValidationIssue(str(path), "schema_error", str(e))
            )
            return False

    def validate_directory(self, directory: Path | str) -> bool:
        """Validate all artifact YAML files in a directory.

        Uses the shared ``iter_artifact_yamls`` traversal so that
        control-metadata directories (``.aplh/``) and template files
        are consistently excluded — exactly the same view that
        ``artifact_loader`` and ``freeze-readiness`` use.
        """
        all_valid = True
        dir_path = Path(directory)

        for yaml_file in iter_artifact_yamls(dir_path):
            if not self.validate_file(yaml_file):
                all_valid = False

        return all_valid
        
    def get_report(self) -> str:
        """Format validation issues as a string report."""
        if not self.issues:
            return "✅ No schema validation issues found."
            
        report = [f"❌ Found {len(self.issues)} schema validation issues:"]
        for issue in self.issues:
            report.append(f"  - [{issue.issue_type}] {issue.file_path}: {issue.message}")
        return "\n".join(report)
