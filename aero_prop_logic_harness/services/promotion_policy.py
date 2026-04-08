"""
Promotion Policy Service (Phase 4).

Evaluates whether candidates meet the rules for promotion to the formal baseline.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Set

from aero_prop_logic_harness.models.promotion import PromotionCandidate, PromotionBlocker
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.audit_correlator import AuditCorrelator
from aero_prop_logic_harness.services.replay_reader import load_trace
from aero_prop_logic_harness.cli import _classify_directory

logger = logging.getLogger(__name__)


class PromotionPolicy:
    """Evaluates promotion rules for candidates."""

    def __init__(self, formal_dir: Path, demo_dir: Path):
        self.formal_dir = formal_dir.resolve()
        self.demo_dir = demo_dir.resolve()
        self.registry = ArtifactRegistry()
        self.correlator = AuditCorrelator(self.demo_dir)
        
        # Load demo registry to analyze artifacts
        try:
            self.registry.load_from_directory(self.demo_dir)
        except Exception:
            pass
            
        self._build_artifact_to_run_index()

    def _build_artifact_to_run_index(self):
        """Map artifact IDs to run IDs that exercised them."""
        self.artifact_to_runs: Dict[str, Set[str]] = {}
        
        traces_dir = self.demo_dir / ".aplh" / "traces"
        if not traces_dir.exists():
            return
            
        for trace_file in traces_dir.glob("run_*.yaml"):
            try:
                trace = load_trace(trace_file)
                run_id = trace.run_id
                if not run_id:
                    continue
                    
                for rec in trace.records:
                    if rec.mode_before:
                        self.artifact_to_runs.setdefault(rec.mode_before, set()).add(run_id)
                    if rec.mode_after:
                        self.artifact_to_runs.setdefault(rec.mode_after, set()).add(run_id)
                    if rec.transition_selected:
                        self.artifact_to_runs.setdefault(rec.transition_selected, set()).add(run_id)
            except Exception:
                pass
                
        # Guards are exercised if their transition is evaluated. Simple approximation:
        # If transition is exercised or considered, the guard was exercised.
        # But for correctness and simplicity, if a run exercised a Transition, it exercised its Guard.
        for art in self.registry.artifacts.values():
            if getattr(art, "artifact_type", None) and art.artifact_type.value == "transition":
                guard_ref = getattr(art, "guard", "")
                if guard_ref:
                    if art.id in self.artifact_to_runs:
                        self.artifact_to_runs.setdefault(guard_ref, set()).update(self.artifact_to_runs[art.id])

    def evaluate_candidate(self, candidate: PromotionCandidate) -> List[PromotionBlocker]:
        """Evaluate a single candidate against promotion rules."""
        blockers = []
        candidate_id = candidate.candidate_id
        
        # 1. Source Classification
        scope = _classify_directory(self.demo_dir)
        if scope != "[Demo-scale]":
            blockers.append(PromotionBlocker(
                blocker_id=f"PB-SRC-{uuid.uuid4().hex[:6]}",
                candidate_id=candidate_id,
                severity="critical",
                check_name="source_classification",
                description=f"Source directory is {scope}, must be [Demo-scale]",
                resolution="Provide a valid demo-scale baseline directory"
            ))
            return blockers  # Fatal

        # 2. Extract artifact details
        art = self.registry.artifacts.get(candidate.artifact_id)
        if art:
            art_id = art.id
            art_type = art.artifact_type.value
            
            if art_type not in ("mode", "transition", "guard"):
                blockers.append(PromotionBlocker(
                    blocker_id=f"PB-TYPE-{uuid.uuid4().hex[:6]}",
                    candidate_id=candidate_id,
                    severity="critical",
                    check_name="valid_type",
                    description=f"Artifact {art_id} is of type {art_type}. Only Phase 2A+ artifacts can be promoted.",
                    resolution="Exclude from promotion manifest."
                ))
        else:
            blockers.append(PromotionBlocker(
                blocker_id=f"PB-MISSING-{uuid.uuid4().hex[:6]}",
                candidate_id=candidate_id,
                severity="critical",
                check_name="artifact_exists",
                description=f"Artifact {candidate.artifact_id} not found in registry.",
                resolution="Ensure file is a valid artifact."
            ))
            return blockers

        # 3. Demo Evidence (Signoff checks)
        # Does this artifact have a trace to a signoff?
        runs_exercising = self.artifact_to_runs.get(art_id, set())
        has_signoff = False
        for r_id in runs_exercising:
            if self.correlator.find_signoffs_for_run(r_id):
                has_signoff = True
                break
                
        if not has_signoff:
            blockers.append(PromotionBlocker(
                blocker_id=f"PB-SIGNOFF-{uuid.uuid4().hex[:6]}",
                candidate_id=candidate_id,
                severity="critical",
                check_name="demo_evidence",
                description=f"Artifact {art_id} has no demo-scale signoffs covering its execution.",
                resolution="Execute a scenario covering this logic and sign it off."
            ))

        # 4. Dependency Rules (TRANS without GUARD)
        if art_type == "transition":
            guard_ref = getattr(art, "guard", "")
            if not guard_ref:
                blockers.append(PromotionBlocker(
                    blocker_id=f"PB-DEP-{uuid.uuid4().hex[:6]}",
                    candidate_id=candidate_id,
                    severity="critical",
                    check_name="dependency_rule",
                    description=f"Transition {art_id} has no guard. Policy requires every transition to have a conditionally checked guard.",
                    resolution="Define a guard and link it through the accepted Transition.guard field."
                ))
                
        return blockers
