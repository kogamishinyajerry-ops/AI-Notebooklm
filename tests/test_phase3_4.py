import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aero_prop_logic_harness.cli import app
from aero_prop_logic_harness.services.decision_tracer import DecisionTrace, TransitionRecord

runner = CliRunner()


@pytest.fixture
def mock_baseline_dir(tmp_path):
    """Sets up a mock baseline directory with .aplh subfolder for testing."""
    baseline = tmp_path / "mock_baseline"
    aplh_dir = baseline / ".aplh"
    aplh_dir.mkdir(parents=True)
    traces_dir = aplh_dir / "traces"
    traces_dir.mkdir()
    
    # Mock gate file so it passes _classify_directory as [Demo-scale]
    gate_file = aplh_dir / "freeze_gate_status.yaml"
    gate_file.write_text("""baseline_scope: demo-scale
boundary_frozen: false
schema_frozen: false
trace_gate_passed: false
baseline_review_complete: false
signed_off_by: null
""")
    return baseline


def create_mock_trace(directory: Path, run_id: str, scenario_id: str) -> Path:
    from aero_prop_logic_harness.services.replay_reader import save_trace
    trace = DecisionTrace(
        run_id=run_id,
        scenario_id=scenario_id
    )
    trace.add_record(
        TransitionRecord(
            tick_id=1,
            mode_before="MODE-0001",
            mode_after="MODE-0001",
            candidates_considered=[],
            transition_selected=None,
            actions_emitted=[],
            block_reason=None,
            applied_signals={}
        )
    )
    return save_trace(trace, directory)


def test_clean_baseline_dry_run_identifies_orphans_and_legacy(mock_baseline_dir):
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    # Create orphan trace
    create_mock_trace(mock_baseline_dir, "RUN-ORPHAN", "SCENARIO-1")
    # Create valid trace
    create_mock_trace(mock_baseline_dir, "RUN-VALID", "SCENARIO-1")
    
    # Create review_signoffs.yaml with 1 valid, 1 legacy, 1 residue
    signoffs_file = mock_baseline_dir / ".aplh" / "review_signoffs.yaml"
    signoffs_data = [
        # Valid
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Real Reviewer",
            "resolution": "Approved",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-VALID",
            "baseline_scope": "demo-scale"
        },
        # Legacy (missing run_id)
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Real Reviewer",
            "resolution": "Approved"
        },
        # Residue
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Demo Reviewer",
            "resolution": "Approved",
            "scenario_id": "SCENARIO-2",
            "run_id": "RUN-RESIDUE",
            "baseline_scope": "demo-scale"
        }
    ]
    with open(signoffs_file, "w") as f:
        yaml.dump(signoffs_data, f)
        
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    def fake_classifier(d: Path) -> str:
        return "[Demo-scale]"
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "clean-baseline",
            "--dir", str(mock_baseline_dir),
            "--dry-run"
        ])
        
        assert result.exit_code == 0
        assert "Orphan traces to be deleted: 1" in result.stdout
        assert "Legacy/Residue signoffs to be removed: 2" in result.stdout
        assert "Remaining valid traces: 1" in result.stdout
        assert "Remaining valid signoffs: 1" in result.stdout
    finally:
        cli._classify_directory = original_classifier


def test_clean_baseline_prune_removes_orphans_and_legacy(mock_baseline_dir):
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    
    orphan_file = create_mock_trace(mock_baseline_dir, "RUN-ORPHAN", "SCENARIO-1")
    valid_file = create_mock_trace(mock_baseline_dir, "RUN-VALID", "SCENARIO-1")
    
    signoffs_file = mock_baseline_dir / ".aplh" / "review_signoffs.yaml"
    signoffs_data = [
        # Valid
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Real",
            "resolution": "Approved",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-VALID",
            "baseline_scope": "demo-scale"
        },
        # Legacy
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Real Reviewer",
            "resolution": "Approved"
        }
    ]
    with open(signoffs_file, "w") as f:
        yaml.dump(signoffs_data, f)
        
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    def fake_classifier(d: Path) -> str:
        return "[Demo-scale]"
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "clean-baseline",
            "--dir", str(mock_baseline_dir),
            "--prune"
        ])
        
        assert result.exit_code == 0
        assert "Successfully removed 1 orphan traces" in result.stdout
        assert "Successfully removed 1 legacy/residue signoffs" in result.stdout
    finally:
        cli._classify_directory = original_classifier
    
    # Verify file deletion
    assert not orphan_file.exists()
    assert valid_file.exists()
    
    # Verify signoffs rewrite
    with open(signoffs_file, "r") as f:
        new_data = yaml.load(f)
    assert len(new_data) == 1
    assert new_data[0]["run_id"] == "RUN-VALID"
    
    # Verify cleanup_log.yaml
    log_file = mock_baseline_dir / ".aplh" / "cleanup_log.yaml"
    assert log_file.exists()
    with open(log_file, "r") as f:
        log_data = yaml.load(f)
    assert len(log_data) == 1
    assert log_data[0]["removed_legacy_signoffs"] == 1
    assert len(log_data[0]["removed_traces"]) == 1
    assert log_data[0]["remaining_traces"] == 1


def test_clean_baseline_rejects_formal_directory(tmp_path):
    # Setup mock formal root (we simulate by an empty dir which is classified as Unmanaged or if we monkeypatch)
    import sys
    from aero_prop_logic_harness.cli import is_formal_baseline_root
    # We will just write a gate file that doesn't say demo-scale
    formal_dir = tmp_path / "formal"
    aplh_dir = formal_dir / ".aplh"
    aplh_dir.mkdir(parents=True)
    gate_file = aplh_dir / "freeze_gate_status.yaml"
    gate_file.write_text("baseline_scope: freeze-complete\n")
    
    # Need to override classification for this test since we want it to be formal
    # Actually wait, _classify_directory uses is_formal_baseline_root which looks at sys.argv[0] and repo root.
    # We just monkeypatch it
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    
    def fake_classifier(d: Path) -> str:
        return "[Formal]"
        
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "clean-baseline",
            "--dir", str(formal_dir),
            "--dry-run"
        ])
        assert result.exit_code == 1
        assert "Cannot clean formal baseline" in result.stdout
    finally:
        cli._classify_directory = original_classifier


def test_clean_baseline_rejects_unmanaged_directory(tmp_path):
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    def fake_classifier(d: Path) -> str:
        return "[Unmanaged]"
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "clean-baseline",
            "--dir", str(tmp_path),
            "--dry-run"
        ])
        assert result.exit_code == 1
        assert "Cleanup is strictly prohibited out of a demo" in result.stdout
    finally:
        cli._classify_directory = original_classifier


def test_audit_correlator_integrity(mock_baseline_dir):
    from aero_prop_logic_harness.services.audit_correlator import AuditCorrelator
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    
    # Create two matched 
    create_mock_trace(mock_baseline_dir, "RUN-OK1", "SCENARIO-1")
    create_mock_trace(mock_baseline_dir, "RUN-OK2", "SCENARIO-1")
    
    # Create an orphan trace
    create_mock_trace(mock_baseline_dir, "RUN-ORPHAN", "SCENARIO-1")
    
    # Create a mismatched scenario ID trace
    create_mock_trace(mock_baseline_dir, "RUN-MISMATCH", "SCENARIO-1")
    
    signoffs_file = mock_baseline_dir / ".aplh" / "review_signoffs.yaml"
    signoffs_data = [
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Rev1",
            "resolution": "App",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-OK1",
            "baseline_scope": "demo-scale"
        },
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Rev2",
            "resolution": "App",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-OK2",
            "baseline_scope": "demo-scale"
        },
        # signoff without trace
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Rev3",
            "resolution": "App",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-NO-TRACE",
            "baseline_scope": "demo-scale"
        },
        # signoff with mismatch scenario_id
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Rev4",
            "resolution": "App",
            "scenario_id": "SCENARIO-2", # trace says SCENARIO-1
            "run_id": "RUN-MISMATCH",
            "baseline_scope": "demo-scale"
        }
    ]
    with open(signoffs_file, "w") as f:
        yaml.dump(signoffs_data, f)
        
    correlator = AuditCorrelator(mock_baseline_dir)
    issues = correlator.verify_correlation_integrity()
    
    assert len(issues) == 3
    
    issue_types = {i.issue_type: i.run_id for i in issues}
    assert issue_types["Missing Trace"] == "RUN-NO-TRACE"
    assert issue_types["Orphan Trace"] == "RUN-ORPHAN"
    assert issue_types["Scenario ID Mismatch"] == "RUN-MISMATCH"
    
    # Check queries
    assert len(correlator.find_runs_for_scenario("SCENARIO-1")) == 5 # OK1, OK2, ORPHAN, MISMATCH (from trace), NO-TRACE (from signoff)
    assert len(correlator.find_signoffs_for_run("RUN-OK1")) == 1
    assert correlator.find_trace_for_run("RUN-OK1") is not None


def test_build_handoff_success(mock_baseline_dir):
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    # Create valid trace
    create_mock_trace(mock_baseline_dir, "RUN-V", "SCENARIO-1")
    
    # Create a scenario file
    scenarios_dir = mock_baseline_dir / "scenarios"
    scenarios_dir.mkdir()
    scenario_file = scenarios_dir / "scenario_1.yml"
    with open(scenario_file, "w") as f:
        yaml.dump({"scenario_id": "SCENARIO-1", "version": "1.0.0"}, f)
    
    # Needs valid signoff
    signoffs_file = mock_baseline_dir / ".aplh" / "review_signoffs.yaml"
    signoffs_data = [
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "reviewer": "Rev1",
            "resolution": "App",
            "scenario_id": "SCENARIO-1",
            "run_id": "RUN-V",
            "baseline_scope": "demo-scale"
        }
    ]
    with open(signoffs_file, "w") as f:
        yaml.dump(signoffs_data, f)
        
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    def fake_classifier(d: Path) -> str:
        return "[Demo-scale]"
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "build-handoff",
            "--dir", str(mock_baseline_dir)
        ])
        
        assert result.exit_code == 0
        assert "Successfully built handoff bundle" in result.stdout
        
        # Verify structure
        handoffs_dir = mock_baseline_dir / ".aplh" / "handoffs"
        bundles = list(handoffs_dir.glob("BUNDLE_*"))
        assert len(bundles) == 1
        bundle_dir = bundles[0]
        
        assert (bundle_dir / "index.yaml").exists()
        assert (bundle_dir / "report.md").exists()
        assert (bundle_dir / "baseline_report.txt").exists()
        assert (bundle_dir / "signoffs.yaml").exists()
        assert (bundle_dir / "scenarios" / "scenario_1.yml").exists()
        
        # It should have 1 trace
        traces = list((bundle_dir / "traces").glob("run_*.yaml"))
        assert len(traces) == 1
        
    finally:
        cli._classify_directory = original_classifier


def test_build_handoff_rejects_no_valid_runs(mock_baseline_dir):
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    # Create orphan trace only
    create_mock_trace(mock_baseline_dir, "RUN-ORPHAN", "SCENARIO-1")
    
    import aero_prop_logic_harness.cli as cli
    original_classifier = cli._classify_directory
    def fake_classifier(d: Path) -> str:
        return "[Demo-scale]"
    cli._classify_directory = fake_classifier
    try:
        result = runner.invoke(app, [
            "build-handoff",
            "--dir", str(mock_baseline_dir)
        ])
        
        assert result.exit_code == 1
        assert "Validation Error: No valid signoffs found" in result.stdout
    finally:
        cli._classify_directory = original_classifier
