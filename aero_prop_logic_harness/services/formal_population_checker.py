"""
Formal Population Checker for Phase 5 Promotion.
Validates the structural integrity of the formal baseline after a physical promotion.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.validators.mode_validator import ModeValidator
from aero_prop_logic_harness.validators.coverage_validator import CoverageValidator
from aero_prop_logic_harness.validators.schema_validator import SchemaValidator
from aero_prop_logic_harness.validators.trace_validator import TraceValidator
from aero_prop_logic_harness.validators.consistency_validator import ConsistencyValidator
from aero_prop_logic_harness.models.promotion import FormalPopulationReport

logger = logging.getLogger(__name__)

class FormalPopulationChecker:
    """Runs immediate post-promotion static analysis checks on the formal baseline."""
    
    def __init__(self, formal_dir: Path):
        self.formal_dir = formal_dir.resolve()
        
    def check_integrity(self) -> Dict[str, str]:
        """
        Runs the full suite of static validators (Phase 2) on the formal baseline.
        Returns a dict of status strings for each validator.
        """
        summary = {}
        
        # 1. Schema Validation
        schema_val = SchemaValidator()
        schema_ok = schema_val.validate_directory(self.formal_dir)
        summary["schema_validation"] = "pass" if schema_ok else "fail"
        
        # Load registry
        registry = ArtifactRegistry()
        try:
            registry.load_from_directory(self.formal_dir)
        except Exception:
            summary["trace_consistency"] = "fail"
            summary["mode_validator"] = "fail"
            summary["coverage_validator"] = "fail"
            return summary
            
        # 2. Trace Validation
        trace_val = TraceValidator(registry)
        trace_ok = trace_val.validate_all()
        
        consist_val = ConsistencyValidator(registry)
        consist_ok = consist_val.validate_all()
        
        summary["trace_consistency"] = "pass" if (trace_ok and consist_ok) else "fail"
        
        # 3. Model Graph Validations
        try:
            graph = ModeGraph.from_registry(registry)
            if graph.mode_count == 0:
                summary["mode_validator"] = "not_applicable"
                summary["coverage_validator"] = "not_applicable"
            else:
                mode_val = ModeValidator(registry, graph)
                mode_ok = mode_val.validate_all()
                summary["mode_validator"] = "pass" if mode_ok else "fail"

                cov_val = CoverageValidator(registry, graph)
                cov_ok = cov_val.validate_all()
                summary["coverage_validator"] = "pass" if cov_ok else "fail"
        except Exception:
            summary["mode_validator"] = "fail"
            summary["coverage_validator"] = "fail"
            
        return summary

    def generate_report(self, manifest_id: str) -> FormalPopulationReport:
        """Generate a FormalPopulationReport from the integrity check results."""
        summary = self.check_integrity()
        overall = all(
            v == "pass" or v == "not_applicable"
            for v in summary.values()
        )
        return FormalPopulationReport(
            manifest_id=manifest_id,
            schema_validation=summary.get("schema_validation", "fail"),
            trace_consistency=summary.get("trace_consistency", "fail"),
            mode_validator=summary.get("mode_validator", "fail"),
            coverage_validator=summary.get("coverage_validator", "fail"),
            overall_pass=overall,
        )
