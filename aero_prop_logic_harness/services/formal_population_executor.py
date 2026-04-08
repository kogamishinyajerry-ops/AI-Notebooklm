"""
Phase 7 controlled formal baseline population.

This service copies only allowlisted demo artifact source files into the formal
baseline, requires an explicit reviewed population approval record, validates in
a sandbox before real writes, and then re-enters the accepted Phase 6 readiness
classifier. It never writes freeze signoff state.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import ruamel.yaml

from aero_prop_logic_harness.models.promotion import (
    FormalPopulationApproval,
    FormalPopulationAuditRecord,
    FormalPopulationInventoryItem,
    FormalPopulationResult,
    PromotionAuditRecord,
    PromotionManifest,
)
from aero_prop_logic_harness.services.formal_population_checker import FormalPopulationChecker
from aero_prop_logic_harness.services.freeze_review_preparer import FreezeReviewPreparer
from aero_prop_logic_harness.services.promotion_audit_logger import PromotionAuditLogger
from aero_prop_logic_harness.services.promotion_guardrail import PromotionGuardrail
from aero_prop_logic_harness.services.promotion_manifest_manager import PromotionManifestManager


class FormalPopulationExecutor:
    """Execute the bounded Phase 7 formal source population path."""

    SUPPORTING_DIRS = ("requirements", "functions", "interfaces", "abnormals", "glossary", "trace")
    PHASE2_DIRS = ("modes", "transitions", "guards")
    ALLOWED_SOURCE_DIRS = SUPPORTING_DIRS + PHASE2_DIRS

    def __init__(self, demo_dir: Path, formal_dir: Path):
        self.demo_dir = Path(demo_dir).resolve()
        self.formal_dir = Path(formal_dir).resolve()
        self.aplh_dir = self.formal_dir / ".aplh"
        self.yaml = ruamel.yaml.YAML()
        self.yaml.preserve_quotes = True
        self.guardrail = PromotionGuardrail(self.formal_dir)
        self.manifest_manager = PromotionManifestManager(self.demo_dir)
        self.promotion_audit_logger = PromotionAuditLogger(self.formal_dir)
        self.population_audit_file = self.aplh_dir / "formal_population_audit_log.yaml"

    def load_approval(self, approval_path: Path) -> FormalPopulationApproval:
        """Load and validate the reviewed population approval record."""
        path = Path(approval_path)
        if not path.is_file():
            raise FileNotFoundError(f"Formal population approval not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = self.yaml.load(f)
        approval = FormalPopulationApproval(**data)
        if Path(approval.source_baseline_dir).resolve() != self.demo_dir:
            raise ValueError("Approval source_baseline_dir does not match the requested demo baseline.")
        if Path(approval.formal_baseline_dir).resolve() != self.formal_dir:
            raise ValueError("Approval formal_baseline_dir does not match the requested formal baseline.")
        if tuple(approval.allowed_source_dirs) != self.ALLOWED_SOURCE_DIRS:
            raise ValueError(
                f"Approval allowed_source_dirs must exactly match {list(self.ALLOWED_SOURCE_DIRS)}."
            )
        if not approval.evidence_refs:
            raise ValueError("Approval must cite at least one reviewable evidence reference.")
        return approval

    def build_inventory(self) -> list[FormalPopulationInventoryItem]:
        """Return the deterministic allowlisted inventory for formal population."""
        items: list[FormalPopulationInventoryItem] = []
        for source_dir in self.ALLOWED_SOURCE_DIRS:
            dir_path = (self.demo_dir / source_dir).resolve()
            if not dir_path.is_dir():
                raise ValueError(f"Required demo source directory is missing: {source_dir}")
            artifact_plane = "phase2a" if source_dir in self.PHASE2_DIRS else "supporting"
            for source_path in sorted(dir_path.glob("*.yaml")):
                if source_path.name.endswith(".template.yaml"):
                    continue
                resolved = source_path.resolve()
                try:
                    resolved.relative_to(dir_path)
                except ValueError as exc:
                    raise ValueError(f"Source file escapes allowlisted directory: {source_path}") from exc
                items.append(
                    FormalPopulationInventoryItem(
                        artifact_plane=artifact_plane,
                        source_dir=source_dir,
                        source_path=str(resolved),
                        target_path=f"artifacts/{source_dir}/{source_path.name}",
                        artifact_id=source_path.stem.upper(),
                    )
                )
        return items

    def validate_approval_matches_inventory(
        self,
        approval: FormalPopulationApproval,
        inventory: list[FormalPopulationInventoryItem],
    ) -> None:
        """Ensure approval cardinality matches the exact deterministic inventory."""
        if approval.expected_file_count != len(inventory):
            raise ValueError(
                "Approval expected_file_count does not match source inventory: "
                f"{approval.expected_file_count} != {len(inventory)}"
            )

    def validate_sandbox(self, inventory: list[FormalPopulationInventoryItem], manifest_id: str) -> None:
        """Validate the planned formal source set in a temporary formal root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_formal = Path(tmp_dir) / "artifacts"
            tmp_formal.mkdir(parents=True)

            for item in inventory:
                source = Path(item.source_path)
                target = tmp_formal / Path(*Path(item.target_path).parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            report = FormalPopulationChecker(tmp_formal).generate_report(manifest_id)
            if not report.overall_pass:
                raise ValueError(
                    "Sandbox validation failed; no formal writes issued: "
                    f"{report.model_dump(exclude_none=True)}"
                )

    def preflight_targets(self, inventory: list[FormalPopulationInventoryItem]) -> None:
        """Ensure all targets stay in allowlisted formal directories and do not overwrite files."""
        for item in inventory:
            source = Path(item.source_path)
            if not source.is_file():
                raise ValueError(f"Source artifact missing: {source}")

            if item.artifact_plane == "phase2a":
                target = self.guardrail.resolve_target_path(item.target_path)
            else:
                target = self._resolve_supporting_target(item.target_path)

            if target.exists():
                raise ValueError(f"Formal population refuses to overwrite existing artifact: {target}")

    def populate(self, approval_path: Path) -> FormalPopulationResult:
        """Execute controlled formal population using a reviewed approval record."""
        approval = self.load_approval(approval_path)
        inventory = self.build_inventory()
        self.validate_approval_matches_inventory(approval, inventory)

        manifest_id = f"FORMAL-POP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self.validate_sandbox(inventory, manifest_id)
        self.preflight_targets(inventory)

        phase2_items = [item for item in inventory if item.artifact_plane == "phase2a"]
        populated: list[str] = []
        for item in inventory:
            target = (
                self.guardrail.resolve_target_path(item.target_path)
                if item.artifact_plane == "phase2a"
                else self._resolve_supporting_target(item.target_path)
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(item.source_path), target)
            populated.append(item.target_path)

        manifest = PromotionManifest(
            manifest_id=manifest_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by="Phase7FormalPopulationExecutor",
            formal_baseline_dir=str(self.formal_dir),
            source_baseline_dir=str(self.demo_dir),
            candidates=[
                {
                    "candidate_id": f"PC-{item.artifact_id}",
                    "status": "passed",
                    "source_path": item.source_path,
                    "target_path": item.target_path,
                }
                for item in phase2_items
            ],
            overall_status="ready",
            promotion_decision="approved",
            decision_by=approval.approved_by,
            decision_at=approval.approved_at,
            lifecycle_status="promoted",
        )
        self.manifest_manager.save_manifest(manifest)

        self.promotion_audit_logger.append_record(
            PromotionAuditRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                manifest_id=manifest_id,
                executor="Phase7FormalPopulationExecutor",
                files_promoted=len(phase2_items),
                files_failed=0,
                status="success",
            )
        )
        self._append_population_audit(
            FormalPopulationAuditRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                approval_id=approval.approval_id,
                promotion_manifest_id=manifest_id,
                executor="Phase7FormalPopulationExecutor",
                files_populated=len(populated),
                support_files_populated=len(populated) - len(phase2_items),
                phase2_files_populated=len(phase2_items),
                status="success",
                target_paths=populated,
            )
        )

        readiness = FreezeReviewPreparer(self.formal_dir, self.demo_dir).prepare()
        return FormalPopulationResult(
            success=True,
            approval_id=approval.approval_id,
            promotion_manifest_id=manifest_id,
            files_populated=populated,
            readiness_state=readiness.formal_state,
        )

    def _resolve_supporting_target(self, target_path_str: str) -> Path:
        target_path = Path(target_path_str)
        if not target_path.parts or target_path.parts[0] != "artifacts":
            raise ValueError(f"Target must start with artifacts/: {target_path_str}")
        if len(target_path.parts) < 3:
            raise ValueError(f"Target must include directory and filename: {target_path_str}")
        source_dir = target_path.parts[1]
        if source_dir not in self.SUPPORTING_DIRS:
            raise ValueError(f"Supporting target is not allowlisted: {target_path_str}")

        target = (self.formal_dir / Path(*target_path.parts[1:])).resolve()
        allowed_root = (self.formal_dir / source_dir).resolve()
        try:
            target.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError(f"Target escapes formal supporting boundary: {target_path_str}") from exc
        return target

    def _append_population_audit(self, record: FormalPopulationAuditRecord) -> None:
        self.aplh_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.population_audit_file, "r", encoding="utf-8") as f:
                records = self.yaml.load(f) or []
        except FileNotFoundError:
            records = []
        records.append(record.model_dump(exclude_none=True))
        with open(self.population_audit_file, "w", encoding="utf-8") as f:
            self.yaml.dump(records, f)
