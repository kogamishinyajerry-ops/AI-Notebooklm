"""
Handoff Package Builder for APLH Phase 3-4.

Constructs point-in-time handoff bundles containing traces, signoffs, 
scenario snapshots, and validation summaries.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import ruamel.yaml

from aero_prop_logic_harness.services.audit_correlator import AuditCorrelator
from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.validators.mode_validator import ModeValidator
from aero_prop_logic_harness.validators.coverage_validator import CoverageValidator
from aero_prop_logic_harness.validators.schema_validator import SchemaValidator
from aero_prop_logic_harness.validators.trace_validator import TraceValidator
from aero_prop_logic_harness.validators.consistency_validator import ConsistencyValidator

logger = logging.getLogger(__name__)


class HandoffBuilder:
    """Builds the Enhanced Demo-Scale Handoff package."""

    def __init__(self, baseline_dir: Path):
        self.baseline_dir = baseline_dir.resolve()
        self.aplh_dir = self.baseline_dir / ".aplh"
        self.handoffs_dir = self.aplh_dir / "handoffs"
        self.correlator = AuditCorrelator(self.baseline_dir)
        self.yaml = ruamel.yaml.YAML()

    def _get_bundle_id(self) -> str:
        now = datetime.now(timezone.utc)
        return f"BUNDLE_{now.strftime('%Y%m%d_%H%M%S')}Z"

    def build_bundle(self) -> Path:
        """Create a complete handoff bundle."""
        # 1. Check prerequisites
        if not self.correlator.run_to_signoffs:
            raise ValueError("No valid signoffs found. Baseline must have at least 1 valid run+signoff.")

        # Ensure integrity
        issues = self.correlator.verify_correlation_integrity()
        valid_runs = []
        for run_id in self.correlator.run_to_signoffs:
            has_trace = self.correlator.find_trace_for_run(run_id) is not None
            # only include complete chains
            if has_trace:
                valid_runs.append(run_id)

        if not valid_runs:
            raise ValueError("No complete run->trace->signoff chains found to bundle.")

        # 2. Setup bundle structure
        bundle_id = self._get_bundle_id()
        bundle_dir = self.handoffs_dir / bundle_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        
        scenarios_dir = bundle_dir / "scenarios"
        traces_dir = bundle_dir / "traces"
        scenarios_dir.mkdir()
        traces_dir.mkdir()

        # 3. Copy traces and gather scenarios
        bundled_scenario_ids = set()
        signoffs_to_bundle = []
        
        runs_included_metadata = []
        stateful_scenarios = {}

        registry = ArtifactRegistry()
        registry_loaded = False
        try:
            registry.load_from_directory(self.baseline_dir)
            registry_loaded = True
        except Exception:
            pass

        def get_stateful_ops(predicate) -> set:
            ops = set()
            if hasattr(predicate, 'operator'):
                val = predicate.operator.value if hasattr(predicate.operator, 'value') else predicate.operator
                if val in ('hysteresis_band', 'sustained_gt', 'sustained_lt'):
                    ops.add(val)
            elif hasattr(predicate, 'operands'):
                for op in getattr(predicate, 'operands', []):
                    ops.update(get_stateful_ops(op))
            return ops

        for run_id in valid_runs:
            trace_path = self.correlator.find_trace_for_run(run_id)
            if not trace_path:
                continue
                
            scenario_id = self.correlator.run_to_scenario.get(run_id)
            
            # Copy trace
            dest_trace_path = traces_dir / trace_path.name
            shutil.copy2(trace_path, dest_trace_path)
            
            # Add signoffs
            signoffs = self.correlator.find_signoffs_for_run(run_id)
            for s in signoffs:
                signoffs_to_bundle.append(s.model_dump(exclude_none=True))
                
            if scenario_id:
                bundled_scenario_ids.add(scenario_id)

            is_richer = False
            stateful_operators = set()
            try:
                trace_data = load_yaml(dest_trace_path)
                # TD-P4-1 lookup evaluator_mode directly
                # fallback to checking records if legacy trace doesn't have it
                evaluator_mode = trace_data.get("evaluator_mode")
                if evaluator_mode is None:
                    for rec in trace_data.get("records", []):
                        reason = rec.get("block_reason", "")
                        if reason and ("HYSTERESIS_BAND" in reason or "SUSTAINED" in reason or "DELTA" in reason):
                            evaluator_mode = "richer"
                            break
                    evaluator_mode = evaluator_mode or "baseline"
                is_richer = evaluator_mode == "richer"

                # TD-P4-2: extract logic directly from artifact guards instead of grep
                if is_richer and registry_loaded:
                    visited_modes = set()
                    for rec in trace_data.get("records", []):
                        if rec.get("mode_before"): visited_modes.add(rec.get("mode_before"))
                        if rec.get("mode_after"): visited_modes.add(rec.get("mode_after"))
                    
                    for art in registry.artifacts.values():
                        if hasattr(art, "source") and hasattr(art, "guard_id"):
                            if art.source in visited_modes and art.guard_id:
                                guard = registry.artifacts.get(art.guard_id)
                                if guard and hasattr(guard, "predicate") and guard.predicate:
                                    ops = get_stateful_ops(guard.predicate)
                                    stateful_operators.update(ops)
            except Exception:
                pass
                
            if scenario_id and stateful_operators:
                if scenario_id not in stateful_scenarios:
                    stateful_scenarios[scenario_id] = set()
                stateful_scenarios[scenario_id].update(stateful_operators)

            runs_included_metadata.append({
                "run_id": run_id,
                "scenario_id": scenario_id,
                "trace_path": f"traces/{dest_trace_path.name}",
                "evaluator_mode": "richer" if is_richer else "baseline",
                "signoff_count": len(signoffs),
                "signoff_reviewers": [s.reviewer for s in signoffs]
            })

        # 4. Write signoffs.yaml
        signoffs_file = bundle_dir / "signoffs.yaml"
        with open(signoffs_file, "w", encoding="utf-8") as f:
            self.yaml.dump(signoffs_to_bundle, f)

        # 5. Copy included scenarios
        scenarios_included_metadata = []
        source_scenarios_dir = self.baseline_dir / "scenarios"
        if source_scenarios_dir.exists():
            for scn_file in source_scenarios_dir.glob("*.yml"):
                try:
                    data = load_yaml(scn_file)
                    sid = data.get("scenario_id")
                    if sid in bundled_scenario_ids:
                        dest_scn_path = scenarios_dir / scn_file.name
                        shutil.copy2(scn_file, dest_scn_path)
                        scenarios_included_metadata.append({
                            "scenario_id": sid,
                            "source_path": f"scenarios/{dest_scn_path.name}",
                            "version": data.get("version", "1.0.0")
                        })
                except Exception:
                    pass

        # 6. Run Baseline Validation targeting baseline_dir
        val_summary = self._generate_baseline_report(bundle_dir / "baseline_report.txt")

        # 7. Generate index.yaml
        stateful_advisory = []
        for sid, ops in stateful_scenarios.items():
            stateful_advisory.append({
                "scenario_id": sid,
                "operators_with_side_effects": sorted(list(ops)),
                "note": "These operators modify RuntimeState history or hysteresis states during evaluation."
            })

        index_metadata = {
            "bundle_id": bundle_id,
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
            "baseline_dir": str(self.baseline_dir.name),
            "baseline_scope": "demo-scale",
            "scenarios_included": scenarios_included_metadata,
            "runs_included": runs_included_metadata,
            "validation_summary": val_summary,
            "stateful_operator_advisory": stateful_advisory
        }
        
        index_file = bundle_dir / "index.yaml"
        with open(index_file, "w", encoding="utf-8") as f:
            self.yaml.dump(index_metadata, f)
            
        # 8. Generate report.md
        self._generate_report(bundle_dir / "report.md", index_metadata, issues)

        return bundle_dir

    def _generate_baseline_report(self, dest_file: Path) -> Dict[str, str]:
        """Runs standard validations and dumps output to a text file."""
        lines = []
        lines.append("=== APLH Baseline Validation Report ===")
        lines.append(f"Target: {self.baseline_dir}")
        lines.append(f"Timestamp: {datetime.now(timezone.utc).isoformat()}Z")
        lines.append("=" * 40 + "\n")
        
        summary = {}
        
        # 1. Schema Validation
        lines.append("--- [1] Schema Validation ---")
        schema_val = SchemaValidator()
        schema_ok = schema_val.validate_directory(self.baseline_dir)
        lines.append(schema_val.get_report())
        summary["validate_artifacts"] = "pass" if schema_ok else "fail"
        
        # Load registry
        registry = ArtifactRegistry()
        try:
            registry.load_from_directory(self.baseline_dir)
        except Exception as e:
            lines.append(f"FATAL: Could not load registry: {e}")
            summary["validate_artifacts"] = "fail"
            summary["check_trace"] = "fail"
            summary["mode_validator"] = "fail"
            summary["coverage_validator"] = "fail"
            with open(dest_file, "w") as f:
                f.write("\n".join(lines))
            return summary

        # 2. Trace Validation
        lines.append("\n--- [2] Trace Consistency ---")
        trace_val = TraceValidator(registry)
        trace_ok = trace_val.validate_all()
        lines.append(trace_val.get_report())
        
        consist_val = ConsistencyValidator(registry)
        consist_ok = consist_val.validate_all()
        lines.append(consist_val.get_report())
        summary["check_trace"] = "pass" if (trace_ok and consist_ok) else "fail"
        
        # 3. ModeGraph validations
        # Catch case where Phase 2 isn't present
        try:
            graph = ModeGraph.from_registry(registry)
            if graph.mode_count == 0:
                summary["mode_validator"] = "not_applicable"
                summary["coverage_validator"] = "not_applicable"
                lines.append("\nNo ModeGraph artifacts present.")
            else:
                lines.append("\n--- [3] Mode Validator ---")
                mode_val = ModeValidator(registry, graph)
                mode_ok = mode_val.validate_all()
                lines.append(mode_val.get_report())
                summary["mode_validator"] = "pass" if mode_ok else "fail"

                lines.append("\n--- [4] Coverage Validator ---")
                cov_val = CoverageValidator(registry, graph)
                cov_ok = cov_val.validate_all()
                lines.append(cov_val.get_report())
                summary["coverage_validator"] = "pass" if cov_ok else "fail"
        except Exception as e:
            lines.append(f"\nModeGraph failure: {e}")
            summary["mode_validator"] = "fail"
            summary["coverage_validator"] = "fail"
            
        with open(dest_file, "w") as f:
            f.write("\n".join(lines))
            
        return summary

    def _generate_report(self, dest_file: Path, idx: Dict[str, Any], issues: List[Any]) -> None:
        """Generates the human-readable markdown report."""
        lines = [
            f"# APLH Enhanced Demo-Scale Handoff",
            f"",
            f"**Bundle ID:** `{idx['bundle_id']}`",
            f"**Generated At:** `{idx['generated_at']}`",
            f"**Baseline Dir:** `{idx['baseline_dir']}`",
            f"**Baseline Scope:** `{idx['baseline_scope']}`",
            f"",
            f"## Statement of Source Objectivity",
            f"",
            f"> **IMPORTANT:** This report is a convenience summary (Level 3). It is not the source of truth. ",
            f"> For rigorous auditing, reviewers must verify the raw trace and signoff files (Level 0) ",
            f"> included in this bundle structure. If this report contradicts the raw traces, the traces prevail.",
            f"",
            f"## 1. Included Scenarios",
        ]
        
        if not idx["scenarios_included"]:
            lines.append("*(No scenarios mapped)*")
        for scn in idx["scenarios_included"]:
            lines.append(f"- **{scn['scenario_id']}** (v{scn['version']}, file: `{scn['source_path']}`)")
            
        lines.append("\n## 2. Included Execution Traces (Runs)")
        
        if not idx["runs_included"]:
            lines.append("*(No runs included)*")
        for run in idx["runs_included"]:
            revs = ", ".join(run["signoff_reviewers"])
            lines.append(
                f"- **{run['run_id']}** (Scenario: {run['scenario_id']}, Evaluator: {run['evaluator_mode']})"
            )
            lines.append(f"  - Associated Signoffs: **{run['signoff_count']}** (Reviewers: {revs})")
            lines.append(f"  - Trace path: `{run['trace_path']}`")

        lines.append(f"\n## 3. Stateful Operator Advisory")
        
        if not idx["stateful_operator_advisory"]:
            lines.append("No scenarios in this bundle use operators with stateful side effects.")
        else:
            lines.append("> [!WARNING]")
            lines.append("> The following scenarios utilize evaluation operators that carry state between execution ticks.")
            lines.append("> Reviewers must account for `RuntimeState` memory when assessing logic correctness.")
            lines.append("")
            
            for adv in idx["stateful_operator_advisory"]:
                ops = ", ".join(adv["operators_with_side_effects"])
                lines.append(f"- **{adv['scenario_id']}**: Uses `{ops}`. {adv['note']}")

        lines.append("\n## 4. Integrity and Validation")
        
        lines.append("### Bundle Correlation Check")
        warnings = [iss for iss in issues if iss.issue_type != "Orphan Trace"]
        advisory_orphans = [iss for iss in issues if iss.issue_type == "Orphan Trace"]
        
        if warnings:
            lines.append("⚠️ **Issues Detected:**")
            for iss in warnings:
                lines.append(f"- `[{iss.issue_type}]` Run {iss.run_id}: {iss.description}")
        else:
            lines.append("✅ Trace-to-Signoff correlation chains are perfectly intact.")
            
        if advisory_orphans:
            lines.append("\n*Advisory: In-Progress Runs Detected*")
            for iss in advisory_orphans:
                lines.append(f"- Run {iss.run_id} has a trace but no signoff. This is normal for runs pending T2 review or successful runs not requiring signoff.")
            
        lines.append("\n### Baseline Validation Status")
        for k, v in idx["validation_summary"].items():
            sym = "✅" if v == "pass" else ("⚠️" if v == "not_applicable" else "❌")
            lines.append(f"- `{k}`: {sym} {v}")
            
        lines.append("\n---\n*End of Handoff Report*")
        
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
