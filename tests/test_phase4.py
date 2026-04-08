"""
Tests for Phase 4 implementation (Formal Readiness / Controlled Promotion).
Validates Gates P4-A to P4-F, plus regression tests for review-round blockers.
"""

import pytest
import shutil
import subprocess
import sys
from pathlib import Path

from aero_prop_logic_harness.services.readiness_assessor import ReadinessAssessor
from aero_prop_logic_harness.services.promotion_policy import PromotionPolicy
from aero_prop_logic_harness.services.evidence_checker import EvidenceChecker
from aero_prop_logic_harness.models.promotion import PromotionCandidate, PromotionBlocker

# Resolve project root once
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Helper: run an APLH CLI command via subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "aero_prop_logic_harness", *args],
        capture_output=True, text=True, cwd=str(_PROJECT_ROOT),
    )


def _backup_tree(path: Path, tmp_path: Path) -> Path | None:
    """Snapshot a repo fixture directory before a CLI test mutates it."""
    if not path.exists():
        return None
    backup_path = tmp_path / path.name
    shutil.copytree(path, backup_path)
    return backup_path


def _restore_tree(path: Path, backup_path: Path | None) -> None:
    """Remove test-generated content and restore any pre-existing fixture tree."""
    if path.exists():
        shutil.rmtree(path)
    if backup_path is not None:
        shutil.copytree(backup_path, path)


# ── Original Phase 4 tests ──────────────────────────────────────────────

def test_p4a_frozen_contracts():
    """Gate P4-A: Frozen Input Preserved."""
    from aero_prop_logic_harness.models.trace import VALID_TRACE_DIRECTIONS
    # Must remain unchanged
    assert len(VALID_TRACE_DIRECTIONS) == 25


def test_p4c_readiness_assessment_empty_formal(tmp_path):
    """Gate P4-C: Readiness Assessment Correctness (Empty Formal)."""
    formal_dir = tmp_path / "artifacts"
    demo_dir = tmp_path / "artifacts" / "examples" / "minimal_demo_set"
    
    assessor = ReadinessAssessor(formal_dir, demo_dir)
    report = assessor.assess()
    
    assert report.overall_status == "not_ready"
    assert report.prerequisites[0].id == "PRE-1"
    assert report.prerequisites[0].status == "not_met"
    
    assert report.prerequisites[3].id == "PRE-4"
    assert report.prerequisites[3].status == "not_met"  # no demo evidence in tmp_path
    
    assert len(report.blockers) > 0


def test_p4d_promotion_policy_soundness(tmp_path):
    """Gate P4-D: Promotion Policy Soundness."""
    formal_dir = tmp_path / "artifacts"
    demo_dir = Path("artifacts/examples/minimal_demo_set").resolve()
    
    policy = PromotionPolicy(formal_dir, demo_dir)
    
    cand = PromotionCandidate(
        candidate_id="PC-TST",
        artifact_type="MODE",
        source_path="modes/test.yaml",
        target_path="artifacts/modes/test.yaml",
        artifact_id="MODE-TST",
        nominated_by="Test",
        nominated_at="2026-04-06T12:00:00Z",
        demo_evidence={},
        validation_status="pending"
    )
    
    blockers = policy.evaluate_candidate(cand)
    print(f"BLOCKERS ARE: {blockers}")
    # Should be blocked because artifact missing and no signoffs
    assert any(b.check_name == "artifact_exists" for b in blockers)


def test_p4e_formal_boundary_non_violation(tmp_path):
    """Gate P4-E: Formal Boundary Non-Violation."""
    formal_dir = tmp_path / "formal_baseline"
    demo_dir = tmp_path / "artifacts" / "examples" / "minimal_demo_set"
    demo_dir.mkdir(parents=True)
    
    # Run evidence checker
    checker = EvidenceChecker(formal_dir, demo_dir)
    cand = PromotionCandidate(
        candidate_id="PC-TST",
        artifact_type="MODE",
        source_path="modes/test.yaml",
        target_path="artifacts/modes/test.yaml",
        artifact_id="MODE-TST",
        nominated_by="Test",
        nominated_at="2026-04-06T12:00:00Z",
        demo_evidence={},
        validation_status="pending"
    )
    
    blockers = checker.check_evidence([cand])
    # Still shouldn't write to formal_dir!
    assert not formal_dir.exists(), "Evidence checker wrote to formal baseline!"


# ── Regression tests for review-round blockers ──────────────────────────

def test_no_art_path_attribute():
    """P1 regression: artifact Pydantic models must never have _path."""
    from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
    registry = ArtifactRegistry()
    registry.load_from_directory(_PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set")
    for art in registry.artifacts.values():
        assert not hasattr(art, '_path'), (
            f"Artifact {art.id} has '_path' — must not exist on Pydantic models"
        )


def test_check_promotion_cli_demo_no_crash(tmp_path):
    """P1+P4: check-promotion CLI must not crash on demo baseline (no AttributeError)."""
    demo_manifests = _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set" / ".aplh" / "promotion_manifests"
    backup = _backup_tree(demo_manifests, tmp_path)
    try:
        result = _run_cli(
            "check-promotion",
            "--demo", "artifacts/examples/minimal_demo_set",
            "--dir", "artifacts",
        )
        assert "AttributeError" not in result.stderr, (
            f"CLI crashed with AttributeError:\n{result.stderr}"
        )
        assert "_path" not in result.stderr, (
            f"_path reference still causing crash:\n{result.stderr}"
        )
        assert "Traceback" not in result.stderr, (
            f"Unexpected traceback:\n{result.stderr}"
        )
    finally:
        _restore_tree(demo_manifests, backup)


def test_check_promotion_cli_formal_no_crash():
    """P1+P4: check-promotion on formal-only dir must not crash."""
    result = _run_cli(
        "check-promotion",
        "--demo", "artifacts",
        "--dir", "artifacts",
    )
    assert "AttributeError" not in result.stderr, f"CLI crashed:\n{result.stderr}"
    assert "Traceback" not in result.stderr, f"Unexpected traceback:\n{result.stderr}"


def test_formal_no_promotion_manifests():
    """P2: formal baseline .aplh/ must not contain promotion_manifests/."""
    formal_manifests = _PROJECT_ROOT / "artifacts" / ".aplh" / "promotion_manifests"
    assert not formal_manifests.exists(), (
        "Formal baseline .aplh/ must not have promotion_manifests/ directory"
    )


def test_formal_no_manifest_write_after_cli(tmp_path):
    """P2: check-promotion must not write manifests to formal .aplh/."""
    demo_manifests = _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set" / ".aplh" / "promotion_manifests"
    formal_manifests = _PROJECT_ROOT / "artifacts" / ".aplh" / "promotion_manifests"
    backup = _backup_tree(demo_manifests, tmp_path)
    try:
        _run_cli(
            "check-promotion",
            "--demo", "artifacts/examples/minimal_demo_set",
            "--dir", "artifacts",
        )
        assert not formal_manifests.exists(), (
            "check-promotion wrote promotion_manifests to formal baseline!"
        )
        # Verify manifest went to demo baseline instead
        assert demo_manifests.exists(), (
            "Manifest should have been written to demo baseline .aplh/"
        )
    finally:
        _restore_tree(demo_manifests, backup)


def test_pre6_not_hardcoded():
    """P3: PRE-6 must not use hardcoded test count."""
    assessor = ReadinessAssessor(
        _PROJECT_ROOT / "artifacts",
        _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set",
    )
    report = assessor.assess()
    pre6 = [p for p in report.prerequisites if p.id == "PRE-6"][0]
    assert "285" not in pre6.detail, (
        f"PRE-6 still uses hardcoded test count: {pre6.detail}"
    )
