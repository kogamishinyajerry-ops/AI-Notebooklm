"""
Phase 7 bounded formal population tests.

Covers allowlists, policy alignment, evidence intake, sandbox validation,
controlled writes, audit behavior, Phase 6 reassessment, and freeze isolation.
"""

from pathlib import Path
import shutil

import pytest
import ruamel.yaml
from typer.testing import CliRunner

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.models.promotion import PromotionCandidate
from aero_prop_logic_harness.services.formal_population_executor import FormalPopulationExecutor
from aero_prop_logic_harness.services.promotion_policy import PromotionPolicy

runner = CliRunner()
yaml = ruamel.yaml.YAML()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEMO_FIXTURE = _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set"


def _write_freeze_status(formal_dir: Path) -> str:
    text = (
        'baseline_scope: "freeze-complete"\n'
        "boundary_frozen: false\n"
        "schema_frozen: false\n"
        "trace_gate_passed: false\n"
        "baseline_review_complete: false\n"
        'signed_off_by: "PENDING"\n'
        'signed_off_at: "2099-12-31T23:59:59Z"\n'
    )
    aplh = formal_dir / ".aplh"
    aplh.mkdir(parents=True, exist_ok=True)
    (aplh / "freeze_gate_status.yaml").write_text(text, encoding="utf-8")
    return text


def _make_phase2_coverage_valid(demo_dir: Path) -> None:
    with open(demo_dir / "modes" / "mode-0002.yaml", "r", encoding="utf-8") as f:
        mode_data = yaml.load(f)
    mode_data["related_abnormals"] = ["ABN-0001"]
    with open(demo_dir / "modes" / "mode-0002.yaml", "w", encoding="utf-8") as f:
        yaml.dump(mode_data, f)

    with open(demo_dir / "abnormals" / "abn-0001.yaml", "r", encoding="utf-8") as f:
        abn_data = yaml.load(f)
    abn_data["related_modes"] = ["MODE-0002"]
    with open(demo_dir / "abnormals" / "abn-0001.yaml", "w", encoding="utf-8") as f:
        yaml.dump(abn_data, f)

    with open(demo_dir / "trace" / "trace-9001.yaml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "id": "TRACE-9001",
                "source_id": "ABN-0001",
                "target_id": "MODE-0002",
                "link_type": "triggers_mode",
                "rationale": "Phase 7 fixture: degraded mode claims the abnormal that triggers it.",
                "confidence": 1.0,
                "review_status": "frozen",
                "created_at": "2026-04-07T00:00:00Z",
                "notes": "",
            },
            f,
        )


def _build_env(tmp_path: Path, *, valid_coverage: bool = True) -> dict[str, Path]:
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    _write_freeze_status(formal_dir)

    demo_dir = tmp_path / "examples" / "minimal_demo_set"
    shutil.copytree(_DEMO_FIXTURE, demo_dir)
    if valid_coverage:
        _make_phase2_coverage_valid(demo_dir)

    return {"formal": formal_dir, "demo": demo_dir}


def _write_approval(env: dict[str, Path], expected_count: int | None = None) -> Path:
    executor = FormalPopulationExecutor(env["demo"], env["formal"])
    inventory = executor.build_inventory()
    approval_path = env["demo"] / ".aplh" / "formal_population_approval.yaml"
    approval = {
        "approval_id": "P7-APPROVAL-TEST",
        "approved_by": "Independent Population Reviewer",
        "approved_at": "2026-04-07T12:00:00Z",
        "decision": "approved",
        "source_baseline_dir": str(env["demo"].resolve()),
        "formal_baseline_dir": str(env["formal"].resolve()),
        "allowed_source_dirs": list(FormalPopulationExecutor.ALLOWED_SOURCE_DIRS),
        "expected_file_count": expected_count if expected_count is not None else len(inventory),
        "evidence_refs": [
            "docs/PHASE7_PLANNING_REVIEW_REPORT.md",
            "docs/PHASE7_FORMAL_POPULATION_PLAN.md",
        ],
        "notes": "Test-only reviewed population approval fixture.",
    }
    with open(approval_path, "w", encoding="utf-8") as f:
        yaml.dump(approval, f)
    return approval_path


def test_phase7_inventory_allowlist_excludes_scenarios_and_runtime_traces(tmp_path):
    env = _build_env(tmp_path)
    executor = FormalPopulationExecutor(env["demo"], env["formal"])

    inventory = executor.build_inventory()
    target_paths = [item.target_path for item in inventory]

    assert len(inventory) == 50
    assert all("/.aplh/" not in item.source_path for item in inventory)
    assert all("/scenarios/" not in item.source_path for item in inventory)
    assert all(not path.startswith("artifacts/scenarios/") for path in target_paths)
    assert all(".aplh/traces" not in item.source_path for item in inventory)
    assert {item.source_dir for item in inventory} == set(FormalPopulationExecutor.ALLOWED_SOURCE_DIRS)


def test_phase7_policy_uses_transition_guard_not_guard_id(tmp_path):
    env = _build_env(tmp_path)
    policy = PromotionPolicy(env["formal"], env["demo"])
    candidate = PromotionCandidate(
        candidate_id="PC-TRANS-0001",
        artifact_type="TRANSITION",
        source_path=str(env["demo"] / "transitions" / "trans-0001.yaml"),
        target_path="artifacts/transitions/trans-0001.yaml",
        artifact_id="TRANS-0001",
        nominated_by="test",
        nominated_at="2026-04-07T12:00:00Z",
        demo_evidence={},
        validation_status="pending",
    )

    blockers = policy.evaluate_candidate(candidate)

    assert not any(blocker.check_name == "dependency_rule" for blocker in blockers)
    assert all("guard_id" not in blocker.description for blocker in blockers)


def test_phase7_population_requires_reviewed_approval(tmp_path):
    env = _build_env(tmp_path)
    executor = FormalPopulationExecutor(env["demo"], env["formal"])

    with pytest.raises(FileNotFoundError):
        executor.populate(env["demo"] / ".aplh" / "missing_approval.yaml")


def test_phase7_sandbox_validation_blocks_invalid_source_set(tmp_path):
    env = _build_env(tmp_path, valid_coverage=False)
    approval = _write_approval(env)
    executor = FormalPopulationExecutor(env["demo"], env["formal"])

    with pytest.raises(ValueError, match="Sandbox validation failed"):
        executor.populate(approval)

    assert not (env["formal"] / "modes").exists()
    assert not (env["formal"] / ".aplh" / "formal_promotions_log.yaml").exists()


def test_phase7_controlled_population_writes_audits_and_reassesses(tmp_path):
    env = _build_env(tmp_path)
    original_freeze = (env["formal"] / ".aplh" / "freeze_gate_status.yaml").read_text(encoding="utf-8")
    approval = _write_approval(env)
    executor = FormalPopulationExecutor(env["demo"], env["formal"])

    result = executor.populate(approval)

    assert result.success is True
    assert len(result.files_populated) == 50
    assert result.readiness_state == "ready_for_freeze_review"

    for dirname in FormalPopulationExecutor.ALLOWED_SOURCE_DIRS:
        assert (env["formal"] / dirname).is_dir()
        assert list((env["formal"] / dirname).glob("*.yaml"))

    assert not (env["formal"] / "scenarios").exists()
    assert not (env["formal"] / ".aplh" / "traces").exists()
    assert (env["formal"] / ".aplh" / "freeze_gate_status.yaml").read_text(encoding="utf-8") == original_freeze

    manifest_path = env["demo"] / ".aplh" / "promotion_manifests" / f"{result.promotion_manifest_id}.yaml"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.load(f)
    assert manifest["lifecycle_status"] == "promoted"
    assert manifest["promotion_decision"] == "approved"
    assert len(manifest["candidates"]) == 9

    with open(env["formal"] / ".aplh" / "formal_promotions_log.yaml", "r", encoding="utf-8") as f:
        promotion_log = yaml.load(f)
    assert promotion_log[-1]["manifest_id"] == result.promotion_manifest_id
    assert promotion_log[-1]["files_promoted"] == 9

    with open(env["formal"] / ".aplh" / "formal_population_audit_log.yaml", "r", encoding="utf-8") as f:
        population_log = yaml.load(f)
    assert population_log[-1]["files_populated"] == 50
    assert population_log[-1]["support_files_populated"] == 41
    assert population_log[-1]["phase2_files_populated"] == 9

    with open(env["formal"] / ".aplh" / "freeze_readiness_report.yaml", "r", encoding="utf-8") as f:
        readiness = yaml.load(f)
    assert readiness["formal_state"] == "ready_for_freeze_review"
    assert readiness["population_state"] == "populated"
    assert readiness["validation_state"] == "post-validated"
    assert readiness["review_preparation_state"] == "ready_for_freeze_review"


def test_phase7_populate_formal_cli_preserves_freeze_isolation(tmp_path):
    env = _build_env(tmp_path)
    original_freeze = (env["formal"] / ".aplh" / "freeze_gate_status.yaml").read_text(encoding="utf-8")
    approval = _write_approval(env)

    result = runner.invoke(app, [
        "populate-formal",
        "--approval", str(approval),
        "--demo", str(env["demo"]),
        "--dir", str(env["formal"]),
    ])

    assert result.exit_code == 0, result.stdout
    assert "freeze-complete was not declared" in result.stdout
    assert (env["formal"] / ".aplh" / "freeze_gate_status.yaml").read_text(encoding="utf-8") == original_freeze

    with open(env["formal"] / ".aplh" / "acceptance_audit_log.yaml", "r", encoding="utf-8") as f:
        acceptance_log = yaml.load(f)
    assert acceptance_log == []
