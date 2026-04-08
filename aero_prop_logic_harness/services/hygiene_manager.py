"""
Hygiene manager for APLH demo baselines.

Provides controlled cleanup of orphan traces, legacy signoffs, and test residues.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import ruamel.yaml
from pydantic import ValidationError

from aero_prop_logic_harness.services.decision_tracer import DecisionTrace
from aero_prop_logic_harness.models.signoff import SignoffEntry
from aero_prop_logic_harness.services.replay_reader import ReplayReader, load_trace

logger = logging.getLogger(__name__)

# Hardcoded whitelist of reviewers used during testing
TEST_RESIDUE_REVIEWERS = ["Demo Reviewer", "Test", "Review A"]

class HygieneManager:
    """Manages cleanup and hygiene for demo-scale baselines."""

    def __init__(self, baseline_dir: Path):
        self.baseline_dir = baseline_dir.resolve()
        self.aplh_dir = self.baseline_dir / ".aplh"
        self.traces_dir = self.aplh_dir / "traces"
        self.signoffs_file = self.aplh_dir / "review_signoffs.yaml"
        self.log_file = self.aplh_dir / "cleanup_log.yaml"
        self.yaml = ruamel.yaml.YAML()

    def _load_signoffs_raw(self) -> List[Dict[str, Any]]:
        """Load raw signoffs data to handle legacy formats without failing validation."""
        if not self.signoffs_file.exists():
            return []
        try:
            with open(self.signoffs_file, "r", encoding="utf-8") as f:
                data = self.yaml.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.warning(f"Failed to parse signoffs file: {e}")
            return []

    def _save_signoffs(self, entries: List[Dict[str, Any]]) -> None:
        """Save raw signoffs data."""
        self.aplh_dir.mkdir(parents=True, exist_ok=True)
        with open(self.signoffs_file, "w", encoding="utf-8") as f:
            self.yaml.dump(entries, f)

    def identify_cleanup_targets(self) -> Dict[str, Any]:
        """
        Identify orphan traces and legacy/residue signoffs.
        Returns a dict:
        {
            "orphan_traces": List[Path],
            "legacy_signoffs": List[Dict], # the raw dicts intended to be removed
            "valid_traces": List[Path],
            "valid_signoffs": List[Dict]
        }
        """
        raw_signoffs = self._load_signoffs_raw()
        valid_signoffs = []
        legacy_signoffs = []
        
        valid_run_ids = set()

        # Phase 1: Filter signoffs
        for entry in raw_signoffs:
            reviewer = entry.get("reviewer", "")
            run_id = entry.get("run_id")
            scenario_id = entry.get("scenario_id")
            
            # Is it legacy? (missing run_id or scenario_id)
            if not run_id or not scenario_id:
                legacy_signoffs.append(entry)
                continue
                
            # Is it test residue?
            if reviewer in TEST_RESIDUE_REVIEWERS:
                legacy_signoffs.append(entry)
                continue
                
            # Is valid (at least has scope="demo-scale" and valid timestamp according to Pydantic)
            try:
                SignoffEntry(**entry)
                valid_signoffs.append(entry)
                valid_run_ids.add(run_id)
            except ValidationError:
                # Malformed entry
                legacy_signoffs.append(entry)

        # Phase 2: Filter traces
        orphan_traces = []
        valid_traces = []
        
        if self.traces_dir.exists() and self.traces_dir.is_dir():
            for trace_file in self.traces_dir.glob("run_*.yaml"):
                if not trace_file.is_file():
                    continue
                try:
                    trace = load_trace(trace_file)
                    # Exclude test run IDs if no valid signoff references them
                    if trace.run_id not in valid_run_ids:
                        orphan_traces.append(trace_file)
                    else:
                        valid_traces.append(trace_file)
                except Exception as e:
                    logger.warning(f"Failed to load trace {trace_file}: {e}")
                    # Unreadable traces are orphans
                    orphan_traces.append(trace_file)

        return {
            "orphan_traces": orphan_traces,
            "legacy_signoffs": legacy_signoffs,
            "valid_traces": valid_traces,
            "valid_signoffs": valid_signoffs
        }
        
    def dry_run(self) -> None:
        """Report what would be cleaned up without making changes."""
        targets = self.identify_cleanup_targets()
        
        print("=== Clean Baseline (Dry-Run) ===")
        print(f"Orphan traces to be deleted: {len(targets['orphan_traces'])}")
        for path in targets["orphan_traces"]:
            print(f"  - {path.name}")
            
        print(f"\nLegacy/Residue signoffs to be removed: {len(targets['legacy_signoffs'])}")
        for entry in targets["legacy_signoffs"]:
            rev = entry.get("reviewer", "<none>")
            r_id = entry.get("run_id", "<none>")
            s_id = entry.get("scenario_id", "<none>")
            print(f"  - Reviewer: {rev}, RunID: {r_id}, ScenarioID: {s_id}")

        print(f"\nRemaining valid traces: {len(targets['valid_traces'])}")
        print(f"Remaining valid signoffs: {len(targets['valid_signoffs'])}")
        print("================================")
        
    def prune(self) -> None:
        """Perform the actual cleanup and log the execution."""
        targets = self.identify_cleanup_targets()
        
        orphan_traces = targets["orphan_traces"]
        legacy_signoffs = targets["legacy_signoffs"]
        valid_signoffs = targets["valid_signoffs"]
        
        removed_traces_paths = []
        
        # 1. Delete orphan traces
        for trace_file in orphan_traces:
            try:
                trace_file.unlink()
                removed_traces_paths.append(str(trace_file.relative_to(self.baseline_dir)))
            except Exception as e:
                logger.error(f"Error removing trace {trace_file}: {e}")
                
        # 2. Save remaining valid signoffs
        if legacy_signoffs or (len(valid_signoffs) == 0 and self.signoffs_file.exists()):
            self._save_signoffs(valid_signoffs)
            
        # 3. Log results
        log_entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "removed_traces": removed_traces_paths,
            "removed_legacy_signoffs": len(legacy_signoffs),
            "remaining_traces": len(targets["valid_traces"]),
            "remaining_signoffs": len(valid_signoffs)
        }
        
        # Append or create log
        logs = []
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    data = self.yaml.load(f)
                    if isinstance(data, list):
                        logs = data
            except Exception:
                pass
                
        logs.append(log_entry)
        
        with open(self.log_file, "w", encoding="utf-8") as f:
            self.yaml.dump(logs, f)
            
        print("=== Clean Baseline (Prune) ===")
        print(f"Successfully removed {len(removed_traces_paths)} orphan traces.")
        print(f"Successfully removed {len(legacy_signoffs)} legacy/residue signoffs.")
        print(f"Remaining valid traces: {log_entry['remaining_traces']}")
        print(f"Remaining valid signoffs: {log_entry['remaining_signoffs']}")
        print(f"Cleanup log written to: {self.log_file.relative_to(self.baseline_dir)}")
        print("==============================")
