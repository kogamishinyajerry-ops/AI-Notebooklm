"""
Tests for Phase 5 Promotion mechanisms.
Covers: actual promotion, formal boundary, post-validation, partial-write/rollback policy,
no implicit freeze decision, manifest/audit. precondition enforcement.
"""
from pathlib import Path
import shutil
from typer.testing import CliRunner
import pytest
import ruamel.yaml

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.models.promotion import (
    PromotionManifest, FormalPopulationReport,
)
from aero_prop_logic_harness.services.promotion_manifest_manager import PromotionManifestManager
from aero_prop_logic_harness.services.promotion_guardrail import PromotionGuardrail

runner = CliRunner()
yaml = ruamel.yaml.YAML()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEMO_FIXTURE = _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set"


def _make_phase2_coverage_valid(demo_dir: Path, formal_dir: Path) -> None:
    """Patch copied fixtures so the promoted graph passes CoverageValidator."""
    with open(demo_dir / "modes" / "mode-0002.yaml", "r", encoding="utf-8") as f:
        mode_data = yaml.load(f)
    mode_data["related_abnormals"] = ["ABN-0001"]
    with open(demo_dir / "modes" / "mode-0002.yaml", "w", encoding="utf-8") as f:
        yaml.dump(mode_data, f)

    with open(formal_dir / "abnormals" / "abn-0001.yaml", "r", encoding="utf-8") as f:
        abn_data = yaml.load(f)
    abn_data["related_modes"] = ["MODE-0002"]
    with open(formal_dir / "abnormals" / "abn-0001.yaml", "w", encoding="utf-8") as f:
        yaml.dump(abn_data, f)

    with open(formal_dir / "trace" / "trace-9001.yaml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "id": "TRACE-9001",
                "source_id": "ABN-0001",
                "target_id": "MODE-0002",
                "link_type": "triggers_mode",
                "rationale": "Coverage fixture: degraded mode claims the abnormal that triggers it.",
                "confidence": 1.0,
                "review_status": "frozen",
                "created_at": "2026-04-07T00:00:00Z",
                "notes": "",
            },
            f,
        )


@pytest.fixture
def phase5_env(tmp_path):
    """Standard Phase 5 test environment with formal + demo dirs and one source artifact."""
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    (formal_dir / ".aplh").mkdir()

    demo_dir = tmp_path / "examples" / "demo"
    demo_dir.mkdir(parents=True)
    manifests_dir = demo_dir / ".aplh" / "promotion_manifests"
    manifests_dir.mkdir(parents=True)

    # Create fake source artifact
    modes_dir = demo_dir / "modes"
    modes_dir.mkdir()
    src_file = modes_dir / "mode-0001.yaml"
    with open(src_file, "w") as f:
        yaml.dump({"artifact_type": "mode", "id": "MODE-0001", "name": "Test Mode"}, f)

    return {
        "formal": formal_dir,
        "demo": demo_dir,
        "manifests": manifests_dir,
        "src_file": src_file,
    }


@pytest.fixture
def phase5_ready_env(tmp_path):
    """A fully-valid promotion environment that can reach post-validated."""
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    (formal_dir / ".aplh").mkdir()

    demo_dir = tmp_path / "examples" / "demo"
    shutil.copytree(_DEMO_FIXTURE, demo_dir)
    manifests_dir = demo_dir / ".aplh" / "promotion_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    # Copy the already-reviewed P0/P1 graph into formal so that promoting
    # Phase 2A artifacts yields a complete, valid formal graph.
    for dirname in ("requirements", "functions", "interfaces", "abnormals", "glossary", "trace"):
        shutil.copytree(_DEMO_FIXTURE / dirname, formal_dir / dirname)

    _make_phase2_coverage_valid(demo_dir, formal_dir)

    candidates = []
    for dirname in ("modes", "transitions", "guards"):
        for yaml_file in sorted((demo_dir / dirname).glob("*.yaml")):
            candidates.append({
                "candidate_id": f"C-{yaml_file.stem.upper()}",
                "status": "passed",
                "source_path": str(yaml_file),
                "target_path": f"artifacts/{dirname}/{yaml_file.name}",
            })

    _write_manifest(
        {
            "formal": formal_dir,
            "demo": demo_dir,
            "manifests": manifests_dir,
        },
        "MAN-READY",
        "ready",
        candidates=candidates,
    )

    return {
        "formal": formal_dir,
        "demo": demo_dir,
        "manifests": manifests_dir,
        "manifest_id": "MAN-READY",
    }


def _write_manifest(env, manifest_id, status, candidates=None):
    """Helper to write a manifest file in the test environment."""
    man_data = {
        "manifest_id": manifest_id,
        "created_at": "2026-04-07T00:00:00Z",
        "created_by": "test",
        "formal_baseline_dir": str(env["formal"]),
        "source_baseline_dir": str(env["demo"]),
        "overall_status": status,
        "promotion_decision": "approved",
        "candidates": candidates or [],
    }
    with open(env["manifests"] / f"{manifest_id}.yaml", "w") as f:
        yaml.dump(man_data, f)


# ── Test 1: Guardrail Safety ─────────────────────────────────────────────

def test_guardrail_safety(phase5_env):
    """P5-C: Guardrail allows only {modes,transitions,guards} and blocks everything else."""
    guardrail = PromotionGuardrail(phase5_env["formal"])

    # Safe paths
    assert guardrail.check_target_safety("artifacts/modes/mode-0001.yaml") is True
    assert guardrail.check_target_safety("artifacts/transitions/t-1.yaml") is True
    assert guardrail.check_target_safety("artifacts/guards/g-1.yaml") is True

    # Unsafe paths — boundary enforcement
    assert guardrail.check_target_safety("artifacts/examples/foo.yaml") is False
    assert guardrail.check_target_safety("artifacts/.aplh/freeze_gate_status.yaml") is False
    assert guardrail.check_target_safety("docs/readme.md") is False
    assert guardrail.check_target_safety("artifacts/modes/../.aplh/freeze_gate_status.yaml") is False
    assert guardrail.check_target_safety("artifacts/modes/../../docs/readme.md") is False


# ── Test 2: Manifest Lifecycle ────────────────────────────────────────────

def test_manifest_manager(phase5_env):
    """P5-B: Manifest lifecycle flows pending -> promoted."""
    mgr = PromotionManifestManager(phase5_env["demo"])

    _write_manifest(phase5_env, "MAN-123", "ready")

    loaded = mgr.load_manifest("MAN-123")
    assert loaded.overall_status == "ready"
    assert loaded.lifecycle_status == "pending"

    mgr.mark_promoted("MAN-123")
    loaded2 = mgr.load_manifest("MAN-123")
    assert loaded2.lifecycle_status == "promoted"


# ── Test 3: Actual Promotion Happy Path ────────────────────────────────────

def test_execute_promotion_success(phase5_ready_env):
    """P5: execute-promotion copies file and writes audit log."""
    result = runner.invoke(app, [
        "execute-promotion", phase5_ready_env["manifest_id"],
        "--demo", str(phase5_ready_env["demo"]),
        "--dir", str(phase5_ready_env["formal"]),
    ])

    assert result.exit_code == 0
    assert "Promotion Successful" in result.stdout

    # Verify files copied
    assert (phase5_ready_env["formal"] / "modes" / "mode-0001.yaml").exists()
    assert (phase5_ready_env["formal"] / "transitions" / "trans-0001.yaml").exists()
    assert (phase5_ready_env["formal"] / "guards" / "guard-0001.yaml").exists()

    # Verify audit log
    log_file = phase5_ready_env["formal"] / ".aplh" / "formal_promotions_log.yaml"
    assert log_file.exists()
    records = yaml.load(log_file)
    assert len(records) == 1
    assert records[0]["manifest_id"] == phase5_ready_env["manifest_id"]
    assert records[0]["files_promoted"] == 9


# ── Test 4: Precondition Not Met — Blocked Manifest ───────────────────────

def test_promotion_blocked_manifest(phase5_env):
    """P5-B: execute-promotion rejects manifest with overall_status != ready."""
    _write_manifest(phase5_env, "MAN-BLOCKED", "blocked", candidates=[
        {
            "candidate_id": "C-1",
            "status": "failed",
            "source_path": str(phase5_env["src_file"]),
            "target_path": "artifacts/modes/mode-0001.yaml",
        }
    ])

    result = runner.invoke(app, [
        "execute-promotion", "MAN-BLOCKED",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    assert result.exit_code == 1
    assert "not in 'ready' state" in result.stdout

    # Verify NO file was copied
    assert not (phase5_env["formal"] / "modes" / "mode-0001.yaml").exists()


# ── Test 5: Precondition Not Met — Already Promoted ───────────────────────

def test_promotion_already_promoted(phase5_env):
    """P5-B: execute-promotion rejects manifest with lifecycle_status=promoted."""
    _write_manifest(phase5_env, "MAN-PROMOTED", "ready", candidates=[
        {
            "candidate_id": "C-1",
            "status": "passed",
            "source_path": str(phase5_env["src_file"]),
            "target_path": "artifacts/modes/mode-0001.yaml",
        }
    ])
    # Manually mark as promoted
    mgr = PromotionManifestManager(phase5_env["demo"])
    mgr.mark_promoted("MAN-PROMOTED")

    result = runner.invoke(app, [
        "execute-promotion", "MAN-PROMOTED",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    assert result.exit_code == 1
    assert "already promoted" in result.stdout


# ── Test 6: Preflight — Missing Source File (No Partial Write) ─────────────

def test_preflight_missing_source(phase5_env):
    """TD-P5-4: preflight detects missing source file and issues 0 writes."""
    missing_file = phase5_env["demo"] / "modes" / "nonexistent.yaml"
    _write_manifest(phase5_env, "MAN-MISSING", "ready", candidates=[
        {
            "candidate_id": "C-MISSING",
            "status": "passed",
            "source_path": str(missing_file),
            "target_path": "artifacts/modes/nonexistent.yaml",
        }
    ])

    result = runner.invoke(app, [
        "execute-promotion", "MAN-MISSING",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    assert result.exit_code == 1
    assert "Preflight" in result.stdout

    # Verify NO file was written to formal
    assert not (phase5_env["formal"] / "modes" / "nonexistent.yaml").exists()
    # Verify NO modes/ directory was created in formal
    assert not (phase5_env["formal"] / "modes").exists()


# ── Test 7: Manifest Not Found ────────────────────────────────────────────

def test_promotion_manifest_not_found(phase5_env):
    """P5: execute-promotion gives controlled error for non-existent manifest."""
    result = runner.invoke(app, [
        "execute-promotion", "NONEXISTENT",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    assert result.exit_code == 1
    assert "not found" in result.stdout.lower() or "Fatal" in result.stdout


# ── Test 8: FormalPopulationReport Model ─────────────────────────────────

def test_formal_population_report_model():
    """P5: FormalPopulationReport Pydantic model validates correctly."""
    report = FormalPopulationReport(
        manifest_id="MAN-TEST",
        schema_validation="pass",
        trace_consistency="pass",
        mode_validator="not_applicable",
        coverage_validator="not_applicable",
        overall_pass=True,
    )
    assert report.overall_pass is True
    assert report.manifest_id == "MAN-TEST"

    # Verify extra fields are forbidden
    with pytest.raises(Exception):
        FormalPopulationReport(
            manifest_id="MAN-TEST",
            schema_validation="pass",
            trace_consistency="pass",
            mode_validator="pass",
            coverage_validator="pass",
            overall_pass=True,
            rogue_field="should_fail",
        )


# ── Test 9: Freeze Gate Status Not Modified ───────────────────────────────

def test_freeze_gate_status_not_modified(phase5_env):
    """P5-D: execute-promotion does not modify freeze_gate_status.yaml."""
    # Create a freeze_gate_status.yaml in formal
    fgs = phase5_env["formal"] / ".aplh" / "freeze_gate_status.yaml"
    with open(fgs, "w") as f:
        yaml.dump({
            "baseline_scope": "freeze-complete",
            "boundary_frozen": False,
            "schema_frozen": False,
            "trace_gate_passed": False,
            "baseline_review_complete": False,
        }, f)

    _write_manifest(phase5_env, "MAN-FGS", "ready", candidates=[
        {
            "candidate_id": "C-1",
            "status": "passed",
            "source_path": str(phase5_env["src_file"]),
            "target_path": "artifacts/modes/mode-0001.yaml",
        }
    ])

    runner.invoke(app, [
        "execute-promotion", "MAN-FGS",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    # Verify freeze_gate_status.yaml unchanged
    with open(fgs) as f:
        data = yaml.load(f)
    assert data["boundary_frozen"] is False
    assert data["schema_frozen"] is False
    assert data["baseline_review_complete"] is False


# ── Test 10: No Implicit Freeze Decision in CLI Output ──────────────────

def test_no_implicit_freeze_in_output(phase5_ready_env):
    """P5-F: CLI output must not contain freeze/accepted/certified wording."""
    result = runner.invoke(app, [
        "execute-promotion", "MAN-READY",
        "--demo", str(phase5_ready_env["demo"]),
        "--dir", str(phase5_ready_env["formal"]),
    ])

    output_lower = result.stdout.lower()
    assert "freeze" not in output_lower, f"CLI output contains 'freeze': {result.stdout}"
    assert "accepted" not in output_lower, f"CLI output contains 'accepted': {result.stdout}"
    assert "certified" not in output_lower, f"CLI output contains 'certified': {result.stdout}"


def test_post_validation_hard_gate_blocks_soft_success(phase5_env):
    """Phase 6: invalid formal population must fail execution even after copy."""
    _write_manifest(phase5_env, "MAN-HARD-GATE", "ready", candidates=[
        {
            "candidate_id": "C-1",
            "status": "passed",
            "source_path": str(phase5_env["src_file"]),
            "target_path": "artifacts/modes/mode-0001.yaml",
        }
    ])

    result = runner.invoke(app, [
        "execute-promotion", "MAN-HARD-GATE",
        "--demo", str(phase5_env["demo"]),
        "--dir", str(phase5_env["formal"]),
    ])

    assert result.exit_code == 1
    assert "post-validated" in result.stdout
    assert "Post-validation hard gate failed" in result.stdout
    assert (phase5_env["formal"] / "modes" / "mode-0001.yaml").exists()


# ── Test 11: Guardrail Preflight No Side Effects ──────────────────────────

def test_guardrail_preflight_no_side_effects(phase5_env):
    """TD-P5-4: preflight_validate must not create directories in formal baseline."""
    guardrail = PromotionGuardrail(phase5_env["formal"])

    operations = [
        {"source": str(phase5_env["src_file"]), "target": "artifacts/modes/mode-0001.yaml"},
    ]

    # Run preflight
    ok, errs = guardrail.preflight_validate(operations)
    assert ok is True
    assert errs == []

    # Verify no directories were created in formal baseline
    assert not (phase5_env["formal"] / "modes").exists(), (
        "preflight_validate must not create directories in formal baseline"
    )
