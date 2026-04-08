"""
Guardrail component for Phase 5 Promotion.
Enforces physical boundary limitations on target paths for actual promotion.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

class PromotionGuardrail:
    """Enforces boundaries during actual physical file copy (Promotion)."""
    
    def __init__(self, formal_dir: Path):
        self.formal_dir = formal_dir.resolve()
        
    def resolve_target_path(self, target_path_str: str) -> Path:
        """
        Resolve a target path into an absolute path inside the formal boundary.

        The only valid logical targets are:
        - artifacts/modes/
        - artifacts/transitions/
        - artifacts/guards/

        Any traversal or directory escape attempt is rejected.
        """
        target_path = Path(target_path_str)
        if not target_path.parts or target_path.parts[0] != "artifacts":
            raise ValueError(f"Target must start with 'artifacts/': {target_path_str}")

        if len(target_path.parts) < 3:
            raise ValueError(f"Target must include an approved subdirectory and filename: {target_path_str}")

        allowed_subdirs = {"modes", "transitions", "guards"}
        subdir = target_path.parts[1]
        if subdir not in allowed_subdirs:
            raise ValueError(f"Target subdirectory '{subdir}' is outside the approved formal boundary")

        resolved = (self.formal_dir / Path(*target_path.parts[1:])).resolve()
        allowed_root = (self.formal_dir / subdir).resolve()

        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(
                f"Target escapes approved formal boundary: {target_path_str}"
            ) from exc

        return resolved

    def check_target_safety(self, target_path_str: str) -> bool:
        """Return True only when the target resolves inside an approved formal directory."""
        try:
            self.resolve_target_path(target_path_str)
            return True
        except Exception:
            return False

    def validate_plan(self, operations: List[dict]) -> Tuple[bool, List[str]]:
        """Validate all target paths in a promotion plan."""
        errors = []
        for op in operations:
            target = op.get("target")
            if not target:
                errors.append("Missing target path in operation.")
                continue
                
            if not self.check_target_safety(target):
                errors.append(f"Unsafe target path bounded out of formal schemas: {target}")
                
        return len(errors) == 0, errors

    def preflight_validate(self, operations: List[dict]) -> Tuple[bool, List[str]]:
        """Preflight: verify all source files exist and all targets are guardrail-safe.

        No directories are created and no files are written during preflight.
        This is the core of the No Partial Write policy: all checks complete
        before the first byte is copied.
        """
        errors = []
        for op in operations:
            src = Path(op["source"])
            tgt = op.get("target", "")

            # Check source file exists
            if not src.is_file():
                errors.append(f"Source file does not exist: {src}")

            # Check target is guardrail-safe
            if not self.check_target_safety(tgt):
                errors.append(f"Unsafe target path: {tgt}")

        return len(errors) == 0, errors
