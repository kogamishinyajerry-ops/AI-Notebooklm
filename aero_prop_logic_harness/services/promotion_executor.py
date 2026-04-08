"""
Promotion Executor for Phase 5.
Executes physical artifact promotion from Demo to Formal boundaries.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from datetime import datetime, timezone

from aero_prop_logic_harness.models.promotion import PromotionResult, PromotionPlan, PromotionAuditRecord
from aero_prop_logic_harness.services.promotion_manifest_manager import PromotionManifestManager
from aero_prop_logic_harness.services.promotion_guardrail import PromotionGuardrail
from aero_prop_logic_harness.services.promotion_audit_logger import PromotionAuditLogger
from aero_prop_logic_harness.services.formal_population_checker import FormalPopulationChecker

logger = logging.getLogger(__name__)

class PromotionExecutor:
    """Executes the controlled physical population path."""
    
    def __init__(self, demo_dir: Path, formal_dir: Path):
        self.demo_dir = demo_dir.resolve()
        self.formal_dir = formal_dir.resolve()
        self.manifest_manager = PromotionManifestManager(self.demo_dir)
        self.guardrail = PromotionGuardrail(self.formal_dir)
        self.audit_logger = PromotionAuditLogger(self.formal_dir)
        self.population_checker = FormalPopulationChecker(self.formal_dir)
        
    def execute(self, manifest_id: str) -> PromotionResult:
        """Executes the promotion of a given manifest."""
        
        # 1. Load and Verify Preconditions (Gate P5-A)
        manifest = self.manifest_manager.load_manifest(manifest_id)
        if manifest.overall_status != "ready":
            raise ValueError(f"Manifest '{manifest_id}' is not in 'ready' state.")
        if manifest.lifecycle_status in ("promoted", "expired"):
            raise ValueError(f"Manifest '{manifest_id}' is already {manifest.lifecycle_status}.")
            
        # 2. Build Plan
        operations = []
        for cand in manifest.candidates:
            if cand.get("status") == "passed":
                src = cand.get("source_path")
                tgt = cand.get("target_path")
                if src and tgt:
                    operations.append({"source": src, "target": tgt})
                
        if not operations:
            raise ValueError("No passed candidates found in manifest with valid paths.")
        plan = PromotionPlan(manifest_id=manifest_id, operations=operations)
            
        # 3. Guardrail validation (Gate P5-B)
        is_safe, errs = self.guardrail.validate_plan(plan.operations)
        if not is_safe:
            raise ValueError(f"Promotion Boundary Violation: {errs}")

        # 3b. Preflight: verify all source files exist (No Partial Write Policy)
        is_preflight_ok, preflight_errs = self.guardrail.preflight_validate(plan.operations)
        if not is_preflight_ok:
            raise ValueError(
                f"Promotion Preflight Failed (0 writes issued): {preflight_errs}"
            )

        # 4. Execute Copy (all preflight checks passed)
        promoted = []
        failed = []
        for op in plan.operations:
            src_path = Path(op["source"])
            
            try:
                actual_tgt = self.guardrail.resolve_target_path(op["target"])
                actual_tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, actual_tgt)
                promoted.append(op["target"])
            except Exception as e:
                logger.error(f"Failed to copy {src_path} -> {op['target']}: {e}")
                failed.append(op["target"])
                
        # 5. Write Audit Log
        overall_status = "success"
        if failed:
            overall_status = "failure" if not promoted else "partial_failure"
            
        record = PromotionAuditRecord(
            timestamp=datetime.now(timezone.utc).isoformat() + "Z",
            manifest_id=manifest_id,
            executor="CLI",
            files_promoted=len(promoted),
            files_failed=len(failed),
            status=overall_status
        )
        self.audit_logger.append_record(record)
        
        # 6. Update Manifest Status
        if promoted:
            self.manifest_manager.mark_promoted(manifest_id)
            
        # 7. Post-Promotion Checker (Gate P5-C)
        population_report = self.population_checker.generate_report(manifest_id)
        post_validation_ok = population_report.overall_pass

        success = overall_status == "success" and post_validation_ok
        error_message = None
        if overall_status != "success":
            error_message = (
                f"Copy execution status={overall_status}; "
                f"post_validation={population_report.model_dump(exclude_none=True)}"
            )
        elif not post_validation_ok:
            error_message = (
                "Post-validation hard gate failed: "
                f"{population_report.model_dump(exclude_none=True)}"
            )

        return PromotionResult(
            manifest_id=manifest_id,
            success=success,
            promoted_files=promoted,
            failed_files=failed,
            error_message=error_message,
        )
