"""
Audit Correlator Service for APLH Phase 3-4.

Builds a memory map correlating traces, scenarios, and signoffs.
Used for building handoff bundles and verifying structural integrity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import ruamel.yaml
from pydantic import ValidationError

from aero_prop_logic_harness.models.signoff import SignoffEntry
from aero_prop_logic_harness.services.replay_reader import ReplayReader, load_trace

logger = logging.getLogger(__name__)


@dataclass
class CorrelationIssue:
    """Represents a break in the correlation chain."""
    issue_type: str
    run_id: Optional[str]
    scenario_id: Optional[str]
    description: str


class AuditCorrelator:
    """Builds a memory index of run_id -> {trace, signoffs, scenario_id}."""

    def __init__(self, baseline_dir: Path):
        self.baseline_dir = baseline_dir.resolve()
        self.aplh_dir = self.baseline_dir / ".aplh"
        self.traces_dir = self.aplh_dir / "traces"
        self.signoffs_file = self.aplh_dir / "review_signoffs.yaml"
        
        self.run_to_trace: Dict[str, Path] = {}
        self.run_to_signoffs: Dict[str, List[SignoffEntry]] = {}
        self.run_to_scenario: Dict[str, str] = {}
        
        self.yaml = ruamel.yaml.YAML(typ="safe")
        self._build_index()

    def _build_index(self) -> None:
        """Scan .aplh directory to build the correlation index."""
        # 1. Load signoffs
        if self.signoffs_file.exists():
            try:
                with open(self.signoffs_file, "r", encoding="utf-8") as f:
                    data = self.yaml.load(f)
                    if isinstance(data, list):
                        for entry_data in data:
                            try:
                                entry = SignoffEntry(**entry_data)
                                if entry.run_id:
                                    if entry.run_id not in self.run_to_signoffs:
                                        self.run_to_signoffs[entry.run_id] = []
                                    self.run_to_signoffs[entry.run_id].append(entry)
                            except ValidationError as e:
                                logger.debug(f"Skipping legacy signoff: {e}")
            except Exception as e:
                logger.error(f"Failed to read signoffs: {e}")
                
        # 2. Load traces
        if self.traces_dir.exists() and self.traces_dir.is_dir():
            for trace_file in self.traces_dir.glob("run_*.yaml"):
                if not trace_file.is_file():
                    continue
                try:
                    trace = load_trace(trace_file)
                    if trace.run_id:
                        self.run_to_trace[trace.run_id] = trace_file
                        # Prefer scenario_id from trace
                        if trace.scenario_id:
                            self.run_to_scenario[trace.run_id] = trace.scenario_id
                except Exception as e:
                    logger.debug(f"Skipping unreadable trace {trace_file.name}: {e}")
                    
        # 3. Augment run_to_scenario from signoffs if missing
        for run_id, signoffs in self.run_to_signoffs.items():
            for s in signoffs:
                if s.scenario_id and run_id not in self.run_to_scenario:
                    self.run_to_scenario[run_id] = s.scenario_id

    def find_signoffs_for_run(self, run_id: str) -> List[SignoffEntry]:
        """Find all signoff entries associated with a run."""
        return self.run_to_signoffs.get(run_id, [])

    def find_runs_for_scenario(self, scenario_id: str) -> List[str]:
        """Find all run_ids associated with a scenario."""
        runs = []
        for run_id, scm_id in self.run_to_scenario.items():
            if scm_id == scenario_id:
                runs.append(run_id)
        return runs

    def find_trace_for_run(self, run_id: str) -> Optional[Path]:
        """Find the trace file associated with a run."""
        return self.run_to_trace.get(run_id)

    def verify_correlation_integrity(self) -> List[CorrelationIssue]:
        """
        Verify that traces and signoffs form complete, valid correlation chains.
        Returns empty list if perfect integrity, otherwise list of issues.
        """
        issues = []
        
        all_run_ids = set(self.run_to_trace.keys()) | set(self.run_to_signoffs.keys())
        
        for run_id in sorted(all_run_ids):
            has_trace = run_id in self.run_to_trace
            scenarios_for_run = set()
            
            if not has_trace:
                issues.append(CorrelationIssue(
                    issue_type="Missing Trace",
                    run_id=run_id,
                    scenario_id=self.run_to_scenario.get(run_id),
                    description=f"Run {run_id} has signoffs but no corresponding trace file."
                ))
            else:
                trace_scenario_id = self.run_to_scenario.get(run_id)
                if trace_scenario_id:
                    scenarios_for_run.add(trace_scenario_id)
            
            signoffs = self.run_to_signoffs.get(run_id, [])
            if not signoffs:
                issues.append(CorrelationIssue(
                    issue_type="Orphan Trace",
                    run_id=run_id,
                    scenario_id=self.run_to_scenario.get(run_id),
                    description=f"Run {run_id} has a trace file but no valid signoff entries."
                ))
            
            for s in signoffs:
                if s.scenario_id:
                    scenarios_for_run.add(s.scenario_id)
                    
            if len(scenarios_for_run) > 1:
                issues.append(CorrelationIssue(
                    issue_type="Scenario ID Mismatch",
                    run_id=run_id,
                    scenario_id=None,
                    description=f"Conflicting scenario IDs found for Run {run_id}: {scenarios_for_run}"
                ))
                
        return issues
