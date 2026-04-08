"""
Evidence Checker Service (Phase 4).

Re-validates candidate artifacts inside the formal baseline structure 
using a temporary dry-run sandbox.
"""

from __future__ import annotations

import tempfile
import shutil
import uuid
from pathlib import Path
from typing import List, Dict

from aero_prop_logic_harness.models.promotion import PromotionCandidate, PromotionBlocker
from aero_prop_logic_harness.validators.schema_validator import SchemaValidator
from aero_prop_logic_harness.validators.trace_validator import TraceValidator
from aero_prop_logic_harness.validators.consistency_validator import ConsistencyValidator
from aero_prop_logic_harness.validators.mode_validator import ModeValidator
from aero_prop_logic_harness.validators.coverage_validator import CoverageValidator
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph


class EvidenceChecker:
    """Performs dry-run dependency and structural checks for promotion candidates."""

    def __init__(self, formal_dir: Path, demo_dir: Path):
        self.formal_dir = formal_dir.resolve()
        self.demo_dir = demo_dir.resolve()

    def check_evidence(self, candidates: List[PromotionCandidate]) -> Dict[str, List[PromotionBlocker]]:
        """
        Verify that promoting the given candidates will not break the formal baseline.
        Returns a mapping of candidate_id -> list of blockers.
        """
        blockers: Dict[str, List[PromotionBlocker]] = {c.candidate_id: [] for c in candidates}
        
        if not candidates:
            return blockers

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            tmp_formal = tmp_root / "artifacts"
            tmp_formal.mkdir(parents=True)
            
            # Copy current formal baseline into sandbox
            if self.formal_dir.exists() and self.formal_dir.is_dir():
                shutil.copytree(self.formal_dir, tmp_formal, dirs_exist_ok=True)
                
            # Copy candidate artifacts into sandbox
            for c in candidates:
                # Resolve source path correctly (often relative to repo or absolute)
                src_path = Path(c.source_path)
                if not src_path.is_absolute():
                    # Fallback relative to current working directory or trying to resolve relative to demo_dir root
                    # Assuming we run from repo root
                    src_path = Path.cwd() / c.source_path
                    if not src_path.exists():
                        src_path = self.demo_dir / Path(c.source_path).name # fallback
                        
                # Target path in sandbox
                # If target path is like "artifacts/modes/mode-1.yaml"
                tgt_rel = Path(c.target_path)
                if tgt_rel.parts[0] == "artifacts":
                    tgt_rel = tgt_rel.relative_to("artifacts")
                
                dest_path = tmp_formal / tgt_rel
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                if src_path.exists():
                    shutil.copy2(src_path, dest_path)
                else:
                    blockers[c.candidate_id].append(PromotionBlocker(
                        blocker_id=f"PB-EVID-MISSING-{uuid.uuid4().hex[:6]}",
                        candidate_id=c.candidate_id,
                        severity="critical",
                        check_name="candidate_source",
                        description=f"Source file {src_path} not found.",
                        resolution="Ensure candidate file exists."
                    ))

            # Run Schema Validator
            schema_val = SchemaValidator()
            if not schema_val.validate_directory(tmp_formal):
                # If schema validation fails, we map to all candidates for now
                report = schema_val.get_report()
                for c in candidates:
                    blockers[c.candidate_id].append(PromotionBlocker(
                        blocker_id=f"PB-EVID-SCHEMA-{uuid.uuid4().hex[:6]}",
                        candidate_id=c.candidate_id,
                        severity="critical",
                        check_name="schema_validation",
                        description="Schema validation failed in sandbox.",
                        resolution="Fix source artifacts prior to promotion."
                    ))
                    
            # Run Trace & Consistency
            registry = ArtifactRegistry()
            try:
                registry.load_from_directory(tmp_formal)
                
                t_val = TraceValidator(registry)
                t_ok = t_val.validate_all()
                if not t_ok:
                    for c in candidates:
                        blockers[c.candidate_id].append(PromotionBlocker(
                            blocker_id=f"PB-EVID-TRACE-{uuid.uuid4().hex[:6]}",
                            candidate_id=c.candidate_id,
                            severity="critical",
                            check_name="trace_validation",
                            description="Trace link validation failed in sandbox (broken links detected).",
                            resolution="Promote required target artifacts simultaneously."
                        ))
                
                c_val = ConsistencyValidator(registry)
                c_ok = c_val.validate_all()
                if not c_ok:
                    for c in candidates:
                        blockers[c.candidate_id].append(PromotionBlocker(
                            blocker_id=f"PB-EVID-CONSIST-{uuid.uuid4().hex[:6]}",
                            candidate_id=c.candidate_id,
                            severity="critical",
                            check_name="consistency_validation",
                            description="Consistency check failed in sandbox.",
                            resolution="Fix semantic trace consistency issues."
                        ))
                        
                # Mode Validation
                graph = ModeGraph.from_registry(registry)
                if graph.mode_count > 0:
                    m_val = ModeValidator(registry, graph)
                    if not m_val.validate_all():
                        for c in candidates:
                            blockers[c.candidate_id].append(PromotionBlocker(
                                blocker_id=f"PB-EVID-MODE-{uuid.uuid4().hex[:6]}",
                                candidate_id=c.candidate_id,
                                severity="critical",
                                check_name="mode_validation",
                                description="ModeGraph validation failed in sandbox (e.g. unreachable modes, multiple defaults).",
                                resolution="Ensure complete sub-graph is promoted."
                            ))
                            
                    # Optional: We don't block on coverage strictly unless it's a promotion policy rule, 
                    # but for P4 dry run, we can just run it
                    
            except Exception as e:
                for c in candidates:
                    blockers[c.candidate_id].append(PromotionBlocker(
                        blocker_id=f"PB-EVID-ERR-{uuid.uuid4().hex[:6]}",
                        candidate_id=c.candidate_id,
                        severity="critical",
                        check_name="registry_load",
                        description=f"Error loading sandbox registry: {e}",
                        resolution="Fix syntax errors."
                    ))
                    
        return blockers
