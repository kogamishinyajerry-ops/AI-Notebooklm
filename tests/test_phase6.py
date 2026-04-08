"""
Phase 6 tests.

Covers: formal state classification, governance-only writers, hard
review-packet assembly, and manual review state reflection.
"""

from pathlib import Path
import shutil

import ruamel.yaml
from typer.testing import CliRunner

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.services.freeze_review_preparer import FreezeReviewPreparer

runner = CliRunner()
yaml = ruamel.yaml.YAML()
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEMO_FIXTURE = _PROJECT_ROOT / "artifacts" / "examples" / "minimal_demo_set"


def _make_phase2_coverage_valid(demo_dir: Path, formal_dir: Path) -> None:
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


def _write_manifest(manifests_dir: Path, formal_dir: Path, demo_dir: Path, manifest_id: str) -> None:
    candidates = []
    for dirname in ("modes", "transitions", "guards"):
        for yaml_file in sorted((demo_dir / dirname).glob("*.yaml")):
            candidates.append({
                "candidate_id": f"C-{yaml_file.stem.upper()}",
                "status": "passed",
                "source_path": str(yaml_file),
                "target_path": f"artifacts/{dirname}/{yaml_file.name}",
            })

    data = {
        "manifest_id": manifest_id,
        "created_at": "2026-04-07T00:00:00Z",
        "created_by": "test",
        "formal_baseline_dir": str(formal_dir),
        "source_baseline_dir": str(demo_dir),
        "overall_status": "ready",
        "promotion_decision": "approved",
        "candidates": candidates,
    }
    with open(manifests_dir / f"{manifest_id}.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _build_ready_env(tmp_path: Path) -> dict[str, Path | str]:
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    (formal_dir / ".aplh").mkdir()

    demo_dir = tmp_path / "examples" / "demo"
    shutil.copytree(_DEMO_FIXTURE, demo_dir)
    manifests_dir = demo_dir / ".aplh" / "promotion_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    for dirname in ("requirements", "functions", "interfaces", "abnormals", "glossary", "trace"):
        shutil.copytree(_DEMO_FIXTURE / dirname, formal_dir / dirname)

    _make_phase2_coverage_valid(demo_dir, formal_dir)
    _write_manifest(manifests_dir, formal_dir, demo_dir, "MAN-P6-READY")
    return {
        "formal": formal_dir,
        "demo": demo_dir,
        "manifest_id": "MAN-P6-READY",
    }


def test_phase6_empty_formal_is_unpopulated_and_writes_governance_files(tmp_path):
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    demo_dir = tmp_path / "examples" / "demo"
    shutil.copytree(_DEMO_FIXTURE, demo_dir)

    report = FreezeReviewPreparer(formal_dir, demo_dir).prepare()

    assert report.formal_state == "unpopulated"
    assert report.population_state == "unpopulated"
    assert report.review_preparation_state == "not_ready"
    assert (formal_dir / ".aplh" / "freeze_readiness_report.yaml").exists()
    assert (formal_dir / ".aplh" / "advisory_resolutions.yaml").exists()
    assert (formal_dir / ".aplh" / "acceptance_audit_log.yaml").exists()

    with open(formal_dir / ".aplh" / "advisory_resolutions.yaml", "r", encoding="utf-8") as f:
        advisories = yaml.load(f)
    assert [item["advisory_id"] for item in advisories] == ["ADV-1", "ADV-2", "ADV-3", "ADV-4"]
    assert all(item["status"] == "closed" for item in advisories)


def test_phase6_assess_readiness_reaches_ready_for_freeze_review(tmp_path):
    env = _build_ready_env(tmp_path)

    result = runner.invoke(app, [
        "execute-promotion", env["manifest_id"],
        "--demo", str(env["demo"]),
        "--dir", str(env["formal"]),
    ])
    assert result.exit_code == 0, result.stdout

    report = FreezeReviewPreparer(env["formal"], env["demo"]).prepare()
    assert report.formal_state == "ready_for_freeze_review"
    assert report.population_state == "populated"
    assert report.validation_state == "post-validated"
    assert report.review_preparation_state == "ready_for_freeze_review"
    assert report.manifest_refs
    assert report.promotion_audit_refs
    assert any("acceptance_audit_log.yaml" in action for action in report.manual_actions_required)
    assert all(gate.passed for gate in report.gate_results if gate.gate_id in {"G6-A", "G6-B", "G6-C", "G6-D"})


def test_phase6_assess_readiness_cli_reports_ready_state(tmp_path):
    env = _build_ready_env(tmp_path)

    promote = runner.invoke(app, [
        "execute-promotion", env["manifest_id"],
        "--demo", str(env["demo"]),
        "--dir", str(env["formal"]),
    ])
    assert promote.exit_code == 0, promote.stdout

    result = runner.invoke(app, [
        "assess-readiness",
        "--dir", str(env["formal"]),
        "--demo", str(env["demo"]),
    ])
    assert result.exit_code == 0, result.stdout
    assert "ready_for_freeze_review" in result.stdout
    assert "Phase 6 Review Packet" in result.stdout


def test_phase6_manual_review_state_is_reflected_but_not_auto_created(tmp_path):
    env = _build_ready_env(tmp_path)

    promote = runner.invoke(app, [
        "execute-promotion", env["manifest_id"],
        "--demo", str(env["demo"]),
        "--dir", str(env["formal"]),
    ])
    assert promote.exit_code == 0, promote.stdout

    acceptance_log = env["formal"] / ".aplh" / "acceptance_audit_log.yaml"
    with open(acceptance_log, "w", encoding="utf-8") as f:
        yaml.dump([
            {
                "timestamp": "2026-04-07T12:00:00Z",
                "actor": "Independent Reviewer",
                "action": "review_packet_acknowledged",
                "state_before": "ready_for_freeze_review",
                "state_after": "accepted_for_review",
                "evidence_refs": ["artifacts/.aplh/freeze_readiness_report.yaml"],
                "notes": "Packet accepted into review queue",
            }
        ], f)

    report = FreezeReviewPreparer(env["formal"], env["demo"]).prepare()
    assert report.formal_state == "accepted_for_review"
    assert any(gate.gate_id == "G6-E" and gate.passed for gate in report.gate_results)


def test_phase6_manual_review_state_cannot_override_failed_machine_readiness(tmp_path):
    formal_dir = tmp_path / "artifacts"
    formal_dir.mkdir()
    (formal_dir / ".aplh").mkdir()
    demo_dir = tmp_path / "examples" / "demo"
    shutil.copytree(_DEMO_FIXTURE, demo_dir)

    acceptance_log = formal_dir / ".aplh" / "acceptance_audit_log.yaml"
    with open(acceptance_log, "w", encoding="utf-8") as f:
        yaml.dump([
            {
                "timestamp": "2026-04-07T12:00:00Z",
                "actor": "Independent Reviewer",
                "action": "review_packet_acknowledged",
                "state_before": "ready_for_freeze_review",
                "state_after": "accepted_for_review",
                "evidence_refs": ["artifacts/.aplh/freeze_readiness_report.yaml"],
                "notes": "Forged/manual entry must not outrank machine readiness.",
            }
        ], f)

    report = FreezeReviewPreparer(formal_dir, demo_dir).prepare()

    assert report.formal_state == "unpopulated"
    assert report.population_state == "unpopulated"
    assert report.validation_state == "not_validated"
    assert report.review_preparation_state == "not_ready"
    assert any(
        gate.gate_id == "G6-E"
        and not gate.passed
        and "cannot pass before ready_for_freeze_review" in gate.detail
        for gate in report.gate_results
    )
