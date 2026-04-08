"""
Phase 6 formal state classification and review-packet preparation.

This service classifies the current formal baseline state without mutating
artifact truth and writes governance-only records under ``artifacts/.aplh/``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

import ruamel.yaml

from aero_prop_logic_harness.models.promotion import (
    AcceptanceAuditEntry,
    AdvisoryResolution,
    FreezeReadinessReport,
    GateResult,
)
from aero_prop_logic_harness.services.formal_population_checker import FormalPopulationChecker
from aero_prop_logic_harness.services.promotion_audit_logger import PromotionAuditLogger
from aero_prop_logic_harness.services.promotion_manifest_manager import PromotionManifestManager
from aero_prop_logic_harness.services.readiness_assessor import ReadinessAssessor


class FreezeReviewPreparer:
    """Classify formal state and assemble the Phase 6 review packet."""

    PROMOTION_DIRS = ("modes", "transitions", "guards")

    def __init__(self, formal_dir: Path, demo_dir: Path):
        self.formal_dir = Path(formal_dir).resolve()
        self.demo_dir = Path(demo_dir).resolve()
        self.aplh_dir = self.formal_dir / ".aplh"
        self.report_path = self.aplh_dir / "freeze_readiness_report.yaml"
        self.advisory_path = self.aplh_dir / "advisory_resolutions.yaml"
        self.acceptance_log_path = self.aplh_dir / "acceptance_audit_log.yaml"
        self.yaml = ruamel.yaml.YAML()
        self.yaml.preserve_quotes = True

    def prepare(self) -> FreezeReadinessReport:
        """Generate governance records and return the current formal state report."""
        self.aplh_dir.mkdir(parents=True, exist_ok=True)

        advisories = self._build_advisory_resolutions()
        self._write_yaml_list(self.advisory_path, advisories)
        acceptance_entries = self._ensure_acceptance_log()

        promoted_manifests = self._load_promoted_manifests()
        audit_records = self._load_promotion_audit_records()
        corroborated_targets, manifest_refs, promotion_audit_refs = self._collect_corroborated_targets(
            promoted_manifests, audit_records
        )

        ghost_targets = sorted(
            target for target in self._list_formal_phase2_targets()
            if target not in corroborated_targets
        )

        population_state = "unpopulated"
        g6a_pass = False
        blocking_conditions: list[str] = []

        phase2_dirs_present = {
            dir_name: any((self.formal_dir / dir_name).glob("*.yaml"))
            for dir_name in self.PROMOTION_DIRS
        }
        has_promoted_targets = len(corroborated_targets) > 0

        if has_promoted_targets:
            population_state = "promoted"

        if has_promoted_targets and all(phase2_dirs_present.values()) and not ghost_targets:
            population_state = "populated"
            g6a_pass = True
        else:
            if not has_promoted_targets:
                blocking_conditions.append(
                    "No corroborated promoted Phase 2A artifacts exist in the formal baseline."
                )
            if has_promoted_targets and not all(phase2_dirs_present.values()):
                missing_dirs = [name for name, present in phase2_dirs_present.items() if not present]
                blocking_conditions.append(
                    f"Formal baseline is missing promoted artifact classes required for populated state: {missing_dirs}"
                )
            if ghost_targets:
                blocking_conditions.append(
                    f"Formal Phase 2A files lack manifest/audit corroboration: {ghost_targets}"
                )

        latest_manifest_id = (
            promoted_manifests[-1].manifest_id if promoted_manifests else "UNPROMOTED"
        )
        population_report = FormalPopulationChecker(self.formal_dir).generate_report(latest_manifest_id)

        validation_state = "not_validated"
        g6b_pass = False
        if population_state == "populated":
            if population_report.overall_pass:
                validation_state = "post-validated"
                g6b_pass = True
            else:
                validation_state = "validation_failed"
                blocking_conditions.append(
                    "Formal post-validation failed; post-validated cannot be claimed."
                )
                blocking_conditions.append(
                    f"FormalPopulationChecker summary: {population_report.model_dump(exclude_none=True)}"
                )
        else:
            blocking_conditions.append(
                "Post-validation is blocked until the formal baseline is fully populated."
            )

        advisory_refs = [
            f"{self.advisory_path}#{entry.advisory_id}" for entry in advisories
        ]
        g6c_pass = all(entry.status == "closed" for entry in advisories)
        if not g6c_pass:
            blocking_conditions.append("One or more Phase 6 advisories remain open.")

        readiness = ReadinessAssessor(self.formal_dir, self.demo_dir).assess()
        if readiness.overall_status != "ready_for_review":
            blocking_conditions.extend(
                f"[{blocker.blocker_id}] {blocker.description}" for blocker in readiness.blockers
            )

        review_preparation_state = "not_ready"
        g6d_pass = False
        if (
            population_state == "populated"
            and validation_state == "post-validated"
            and g6c_pass
            and readiness.overall_status == "ready_for_review"
        ):
            review_preparation_state = "ready_for_freeze_review"
            g6d_pass = True

        manual_state = self._classify_manual_review_state(acceptance_entries)
        formal_state = self._derive_formal_state(
            population_state=population_state,
            validation_state=validation_state,
            review_preparation_state=review_preparation_state,
            manual_state=manual_state,
        )
        manual_review_gate_pass = (
            review_preparation_state == "ready_for_freeze_review"
            and manual_state in {"accepted_for_review", "pending_manual_decision"}
        )
        if manual_state and not manual_review_gate_pass:
            blocking_conditions.append(
                f"Manual review state '{manual_state}' is ignored until the formal baseline reaches ready_for_freeze_review."
            )

        gate_results = [
            GateResult(
                gate_id="G6-A",
                tier="T1",
                passed=g6a_pass,
                detail=(
                    "Formal Phase 2A population is corroborated by promoted manifests and promotion audit records."
                    if g6a_pass
                    else "Population classification remains below populated."
                ),
            ),
            GateResult(
                gate_id="G6-B",
                tier="T1",
                passed=g6b_pass,
                detail=(
                    "Formal baseline passes hard post-validation."
                    if g6b_pass
                    else "Hard post-validation blocks elevation beyond populated/promoted."
                ),
            ),
            GateResult(
                gate_id="G6-C",
                tier="T1",
                passed=g6c_pass,
                detail=(
                    "ADV-1 through ADV-4 are routed and closed in the governance record."
                    if g6c_pass
                    else "Advisory closure is incomplete."
                ),
            ),
            GateResult(
                gate_id="G6-D",
                tier="T1",
                passed=g6d_pass,
                detail=(
                    "Review packet is complete and the formal baseline is ready for independent freeze review."
                    if g6d_pass
                    else "Review packet cannot claim ready_for_freeze_review yet."
                ),
            ),
            GateResult(
                gate_id="G6-E",
                tier="T2",
                passed=manual_review_gate_pass,
                detail=(
                    f"Manual review intake recorded as {manual_state}."
                    if manual_review_gate_pass
                    else (
                        f"Manual review intake state '{manual_state}' is recorded but cannot pass before ready_for_freeze_review."
                        if manual_state
                        else "Manual review intake has not yet been acknowledged."
                    )
                ),
            ),
        ]

        manual_actions_required = self._build_manual_actions(
            formal_state=formal_state,
            review_preparation_state=review_preparation_state,
        )

        report = FreezeReadinessReport(
            report_id=f"FREEZE-READINESS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            formal_baseline_dir=str(self.formal_dir),
            source_demo_dir=str(self.demo_dir),
            formal_state=formal_state,
            population_state=population_state,
            validation_state=validation_state,
            review_preparation_state=review_preparation_state,
            gate_results=gate_results,
            blocking_conditions=blocking_conditions,
            advisory_status_refs=advisory_refs,
            manifest_refs=manifest_refs,
            promotion_audit_refs=promotion_audit_refs,
            manual_actions_required=manual_actions_required,
        )
        self._write_yaml_dict(self.report_path, report.model_dump(exclude_none=True))
        return report

    def _load_promoted_manifests(self):
        manager = PromotionManifestManager(self.demo_dir)
        manifests = manager.list_manifests()
        manifests.sort(key=lambda item: item.created_at)
        return [m for m in manifests if m.lifecycle_status == "promoted"]

    def _load_promotion_audit_records(self) -> list[dict]:
        logger = PromotionAuditLogger(self.formal_dir)
        if not logger.log_file.exists():
            return []
        with open(logger.log_file, "r", encoding="utf-8") as f:
            data = self.yaml.load(f) or []
        if not isinstance(data, list):
            return []
        return [record for record in data if isinstance(record, dict)]

    def _collect_corroborated_targets(self, promoted_manifests, audit_records):
        corroborated_targets: set[str] = set()
        manifest_refs: list[str] = []
        promotion_audit_refs: list[str] = []
        successful_manifests = {
            record["manifest_id"]
            for record in audit_records
            if record.get("manifest_id") and record.get("files_promoted", 0) > 0
        }

        for manifest in promoted_manifests:
            if manifest.manifest_id not in successful_manifests:
                continue
            manifest_path = self.demo_dir / ".aplh" / "promotion_manifests" / f"{manifest.manifest_id}.yaml"
            manifest_refs.append(str(manifest_path))
            promotion_audit_refs.append(
                f"{self.formal_dir / '.aplh' / 'formal_promotions_log.yaml'}#manifest_id={manifest.manifest_id}"
            )
            for candidate in manifest.candidates:
                if candidate.get("status") != "passed":
                    continue
                target = candidate.get("target_path")
                if not target:
                    continue
                actual = self._formal_target_to_path(target)
                if actual.is_file():
                    corroborated_targets.add(target)

        manifest_refs.sort()
        promotion_audit_refs.sort()
        return corroborated_targets, manifest_refs, promotion_audit_refs

    def _list_formal_phase2_targets(self) -> list[str]:
        targets: list[str] = []
        for dir_name in self.PROMOTION_DIRS:
            dir_path = self.formal_dir / dir_name
            if not dir_path.is_dir():
                continue
            for yaml_file in sorted(dir_path.glob("*.yaml")):
                targets.append(f"artifacts/{dir_name}/{yaml_file.name}")
        return targets

    def _formal_target_to_path(self, target_path: str) -> Path:
        path = Path(target_path)
        if not path.parts or path.parts[0] != "artifacts":
            return self.formal_dir / "__invalid__"
        return self.formal_dir / Path(*path.parts[1:])

    def _build_advisory_resolutions(self) -> list[AdvisoryResolution]:
        return [
            AdvisoryResolution(
                advisory_id="ADV-1",
                title="Path traversal protection",
                phase6_subphase="P6-M2",
                priority="P1",
                gate_id="G6-C",
                tier="T1",
                status="closed",
                resolution_rule="Promotion targets must resolve inside artifacts/modes, artifacts/transitions, or artifacts/guards only.",
                evidence_refs=[
                    "aero_prop_logic_harness/services/promotion_guardrail.py",
                    "tests/test_phase5.py",
                    "tests/test_phase6.py",
                ],
                notes="Resolved target-path enforcement now blocks traversal and ghost boundary writes.",
            ),
            AdvisoryResolution(
                advisory_id="ADV-2",
                title="Post-validation becomes hard gate",
                phase6_subphase="P6-M1",
                priority="P1",
                gate_id="G6-B",
                tier="T1",
                status="closed",
                resolution_rule="Post-promotion validation failure must keep execution below post-validated and return a failing execution result.",
                evidence_refs=[
                    "aero_prop_logic_harness/services/promotion_executor.py",
                    "aero_prop_logic_harness/services/freeze_review_preparer.py",
                    "tests/test_phase5.py",
                    "tests/test_phase6.py",
                ],
                notes="Physical copy no longer implies post-validated success.",
            ),
            AdvisoryResolution(
                advisory_id="ADV-3",
                title="PromotionPlan / generate_report integration gap",
                phase6_subphase="P6-M2",
                priority="P2",
                gate_id="G6-D",
                tier="T2",
                status="closed",
                resolution_rule="Promotion execution must use PromotionPlan and post-validation must be sourced from FormalPopulationChecker.generate_report().",
                evidence_refs=[
                    "aero_prop_logic_harness/services/promotion_executor.py",
                    "aero_prop_logic_harness/services/freeze_review_preparer.py",
                    "tests/test_phase6.py",
                ],
                notes="Structured plan/report models are now exercised by the executable path and review-packet assembly.",
            ),
            AdvisoryResolution(
                advisory_id="ADV-4",
                title="Stronger boundary tests",
                phase6_subphase="P6-M2",
                priority="P2",
                gate_id="G6-C",
                tier="T1",
                status="closed",
                resolution_rule="Phase 6 must prove traversal blocking, hard post-validation, state classification, and governance-only writing with tmp_path-backed tests.",
                evidence_refs=[
                    "tests/test_phase5.py",
                    "tests/test_phase6.py",
                ],
                notes="Boundary and state-ladder regressions are covered by dedicated Phase 6 tests.",
            ),
        ]

    def _ensure_acceptance_log(self) -> list[AcceptanceAuditEntry]:
        if not self.acceptance_log_path.exists():
            self._write_yaml_list(self.acceptance_log_path, [])
            return []

        with open(self.acceptance_log_path, "r", encoding="utf-8") as f:
            data = self.yaml.load(f) or []

        if not isinstance(data, list):
            self._write_yaml_list(self.acceptance_log_path, [])
            return []

        entries: list[AcceptanceAuditEntry] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                entries.append(AcceptanceAuditEntry(**item))
            except Exception:
                continue
        return entries

    def _classify_manual_review_state(self, entries: list[AcceptanceAuditEntry]) -> str | None:
        if not entries:
            return None
        latest = entries[-1]
        if latest.state_after in {"accepted_for_review", "pending_manual_decision"}:
            return latest.state_after
        return None

    def _derive_formal_state(
        self,
        population_state: str,
        validation_state: str,
        review_preparation_state: str,
        manual_state: str | None,
    ) -> str:
        if review_preparation_state == "ready_for_freeze_review":
            if manual_state:
                return manual_state
            return "ready_for_freeze_review"
        if validation_state == "post-validated":
            return "post-validated"
        if population_state == "populated":
            return "populated"
        if population_state == "promoted":
            return "promoted"
        return "unpopulated"

    def _build_manual_actions(self, formal_state: str, review_preparation_state: str) -> list[str]:
        if review_preparation_state == "ready_for_freeze_review":
            actions = [
                "Human reviewer may record accepted_for_review or pending_manual_decision in artifacts/.aplh/acceptance_audit_log.yaml.",
                "freeze_gate_status.yaml remains manual-only; do not auto-write freeze-complete.",
            ]
            if formal_state in {"accepted_for_review", "pending_manual_decision"}:
                actions.insert(
                    0,
                    "Manual freeze decision still requires explicit human signoff in artifacts/.aplh/freeze_gate_status.yaml.",
                )
            return actions

        return [
            "Complete formal population with corroborated promoted manifests and promotion audit records.",
            "Resolve formal validation blockers before claiming post-validated.",
            "Build the machine-readable review packet; freeze_gate_status.yaml remains manual-only.",
        ]

    def _write_yaml_dict(self, path: Path, data: dict) -> None:
        if hasattr(data, "model_dump"):
            data = data.model_dump(exclude_none=True)
        with open(path, "w", encoding="utf-8") as f:
            self.yaml.dump(data, f)

    def _write_yaml_list(self, path: Path, data: list) -> None:
        serializable = []
        for item in data:
            if hasattr(item, "model_dump"):
                serializable.append(item.model_dump(exclude_none=True))
            else:
                serializable.append(item)
        with open(path, "w", encoding="utf-8") as f:
            self.yaml.dump(serializable, f)
