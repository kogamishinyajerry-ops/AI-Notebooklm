import pytest
from pathlib import Path
import subprocess
from pydantic import ValidationError

from aero_prop_logic_harness.loaders.artifact_loader import load_artifact, load_artifacts_from_dir
from aero_prop_logic_harness.validators import ConsistencyValidator
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.models import Requirement, TraceLink, TraceLinkType, ArtifactType

def test_type_spoofing(tmp_path):
    # Spoof type: Requirements ID but claims to be a function
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    req_file = req_dir / "req-1234.yaml"
    req_file.write_text('''
id: "REQ-1234"
artifact_type: "function"
title: "T"
description: "D"
    ''')
    
    with pytest.raises(ValueError, match="Type spoofing detected"):
        load_artifact(req_file)

def test_unacknowledged_trace_loop(tmp_path):
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    req_file = req_dir / "req-8000.yaml"
    req_file.write_text('''
id: "REQ-8000"
artifact_type: "requirement"
title: "T"
description: "D"
status: "draft"
review_status: "draft"
provenance:
  source_type: "human_authored"
  method: "manual"
  confidence: 1.0
linked_functions: []
    ''')
    
    func_dir = tmp_path / "functions"
    func_dir.mkdir()
    func_file = func_dir / "func-8000.yaml"
    func_file.write_text('''
id: "FUNC-8000"
artifact_type: "function"
name: "F"
purpose: "P"
status: "draft"
review_status: "draft"
provenance:
  source_type: "human_authored"
  method: "manual"
  confidence: 1.0
    ''')

    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    trace_file = trace_dir / "trace-8000.yaml"
    trace_file.write_text('''
id: "TRACE-8000"
source_id: "REQ-8000"
target_id: "FUNC-8000"
link_type: "implements"
review_status: "draft"
confidence: 1.0
    ''')
    
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "check-trace", "--dir", str(tmp_path)], capture_output=True)
    assert result.returncode == 1
    assert b"TRACE-8000 exists" in result.stdout

def test_baseline_pollution(tmp_path):
    # Setting explicitly --dir artifacts should fail as examples are ignored
    # making the graph 'Empty' (or weak)
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", "artifacts"], capture_output=True)
    assert result.returncode == 1
    # Check if empty graph causes failure
    assert b"Empty Graph Check: \xe2\x9d\x8c Fail (0 traces)" in result.stdout

def test_weak_graph_topology(tmp_path):
    # A proper test should construct enough elements to pass empty graph but fail topological linkage
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    (req_dir / "req-9000.yaml").write_text('id: "REQ-9000"\nartifact_type: "requirement"\ntitle: "T"\ndescription: "D"\nstatus: "draft"\nreview_status: "draft"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\nlinked_functions: ["FUNC-9000"]\n')
    
    func_dir = tmp_path / "functions"
    func_dir.mkdir()
    (func_dir / "func-9000.yaml").write_text('id: "FUNC-9000"\nartifact_type: "function"\nname: "F"\npurpose: "P"\nstatus: "draft"\nreview_status: "draft"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\ndependent_requirements: ["REQ-9000"]\n')
    
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "trace-9000.yaml").write_text('id: "TRACE-9000"\nsource_id: "REQ-9000"\ntarget_id: "FUNC-9000"\nlink_type: "implements"\nreview_status: "draft"\nconfidence: 1.0\n')
    
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(tmp_path)], capture_output=True)
    assert result.returncode == 1
    # Check that relational coverage complains since it has REQ->FUNC but misses ABN->FUNC_OR_IFACE etc.
    assert b"Min Relational Coverage: \xe2\x9d\x8c Fail" in result.stdout

def _create_minimal_passing_graph(tmp_path):
    if not tmp_path.exists():
        tmp_path.mkdir(parents=True)
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    (req_dir / "req-9999.yaml").write_text('id: "REQ-9999"\nartifact_type: "requirement"\ntitle: "T"\ndescription: "D"\nstatus: "draft"\nreview_status: "reviewed"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\n  reviewed_by: "Reviewer"\nlinked_functions: ["FUNC-9999"]\nlinked_interfaces: ["IFACE-9999"]\nlinked_abnormals: ["ABN-9999"]\n')
    
    func_dir = tmp_path / "functions"
    func_dir.mkdir()
    (func_dir / "func-9999.yaml").write_text('id: "FUNC-9999"\nartifact_type: "function"\nname: "F"\npurpose: "P"\nstatus: "draft"\nreview_status: "reviewed"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\n  reviewed_by: "Reviewer"\ndependent_requirements: ["REQ-9999"]\nrelated_interfaces: ["IFACE-9999"]\n')
    
    iface_dir = tmp_path / "interfaces"
    iface_dir.mkdir()
    (iface_dir / "iface-9999.yaml").write_text('id: "IFACE-9999"\nartifact_type: "interface"\nname: "I"\nstatus: "draft"\nreview_status: "reviewed"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\n  reviewed_by: "Reviewer"\nrelated_functions: ["FUNC-9999"]\nrelated_abnormals: ["ABN-9999"]\nrelated_requirements: ["REQ-9999"]\n')

    abn_dir = tmp_path / "abnormals"
    abn_dir.mkdir()
    (abn_dir / "abn-9999.yaml").write_text('id: "ABN-9999"\nartifact_type: "abnormal"\nname: "A"\nstatus: "draft"\nreview_status: "reviewed"\nprovenance:\n  source_type: "human_authored"\n  method: "manual"\n  confidence: 1.0\n  reviewed_by: "Reviewer"\nrelated_interfaces: ["IFACE-9999"]\nrelated_requirements: ["REQ-9999"]\n')

    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "trace-9901.yaml").write_text('id: "TRACE-9901"\nsource_id: "REQ-9999"\ntarget_id: "FUNC-9999"\nlink_type: "implements"\nreview_status: "reviewed"\nconfidence: 1.0\n')
    (trace_dir / "trace-9902.yaml").write_text('id: "TRACE-9902"\nsource_id: "REQ-9999"\ntarget_id: "IFACE-9999"\nlink_type: "constrains"\nreview_status: "reviewed"\nconfidence: 1.0\n')
    (trace_dir / "trace-9903.yaml").write_text('id: "TRACE-9903"\nsource_id: "REQ-9999"\ntarget_id: "ABN-9999"\nlink_type: "relates_to"\nreview_status: "reviewed"\nconfidence: 1.0\n')
    (trace_dir / "trace-9904.yaml").write_text('id: "TRACE-9904"\nsource_id: "FUNC-9999"\ntarget_id: "IFACE-9999"\nlink_type: "uses"\nreview_status: "reviewed"\nconfidence: 1.0\n')
    (trace_dir / "trace-9905.yaml").write_text('id: "TRACE-9905"\nsource_id: "ABN-9999"\ntarget_id: "IFACE-9999"\nlink_type: "affects"\nreview_status: "reviewed"\nconfidence: 1.0\n')
    
    return tmp_path

def test_signoff_file_must_be_target_bound(tmp_path):
    target = _create_minimal_passing_graph(tmp_path / "target")
    # File in wrong location
    wrong = tmp_path / ".aplh"
    wrong.mkdir()
    (wrong / "freeze_gate_status.yaml").write_text('baseline_scope: "demo-scale"\nboundary_frozen: true\nschema_frozen: true\ntrace_gate_passed: true\nbaseline_review_complete: true\nsigned_off_by: "X"\nsigned_off_at: "2026-04-03T12:00:00Z"\n')
    
    import sys
    # Calling on target, missing .aplh inside it
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(target)], capture_output=True)
    assert result.returncode == 1
    assert b"Target baseline must contain '.aplh/freeze_gate_status.yaml'" in result.stdout

def test_signoff_rejects_quoted_bool(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    aplh = target / ".aplh"
    aplh.mkdir()
    (aplh / "freeze_gate_status.yaml").write_text('baseline_scope: "demo-scale"\nboundary_frozen: "true"\nschema_frozen: true\ntrace_gate_passed: true\nbaseline_review_complete: true\nsigned_off_by: "X"\nsigned_off_at: "2026-04-03T12:00:00Z"\n')
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(target)], capture_output=True)
    assert result.returncode == 1
    assert b"Signoff schema validation failed" in result.stdout

def test_signoff_rejects_blank_signer(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    aplh = target / ".aplh"
    aplh.mkdir()
    (aplh / "freeze_gate_status.yaml").write_text('baseline_scope: "demo-scale"\nboundary_frozen: true\nschema_frozen: true\ntrace_gate_passed: true\nbaseline_review_complete: true\nsigned_off_by: "   "\nsigned_off_at: "2026-04-03T12:00:00Z"\n')
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(target)], capture_output=True)
    assert result.returncode == 1
    assert b"Signoff schema validation failed" in result.stdout

def test_signoff_rejects_invalid_datetime(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    aplh = target / ".aplh"
    aplh.mkdir()
    (aplh / "freeze_gate_status.yaml").write_text('baseline_scope: "demo-scale"\nboundary_frozen: true\nschema_frozen: true\ntrace_gate_passed: true\nbaseline_review_complete: true\nsigned_off_by: "X"\nsigned_off_at: "2026-13-40T25:61:61Z"\n')
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(target)], capture_output=True)
    assert result.returncode == 1
    assert b"Signoff schema validation failed" in result.stdout

def test_signoff_missing_file_fails(tmp_path):
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(tmp_path)], capture_output=True)
    assert result.returncode == 1
    assert b"Target baseline must contain '.aplh/freeze_gate_status.yaml'" in result.stdout

def test_freeze_readiness_demo_scope_output_is_not_freeze_complete(tmp_path):
    target = _create_minimal_passing_graph(tmp_path / "target")
    aplh = target / ".aplh"
    aplh.mkdir()
    (aplh / "freeze_gate_status.yaml").write_text('baseline_scope: "demo-scale"\nboundary_frozen: true\nschema_frozen: true\ntrace_gate_passed: true\nbaseline_review_complete: true\nsigned_off_by: "X"\nsigned_off_at: "2026-04-03T12:00:00Z"\n')
    
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(target)], capture_output=True)
    if result.returncode != 0:
        trace_result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "check-trace", "--dir", str(target)], capture_output=True)
        print("TRACE OUTPUT:\n" + trace_result.stdout.decode())
    assert result.returncode == 0
    assert b"Demo-scale gate checks passed" in result.stdout
    assert b"Ready for Formal Baseline Freeze" not in result.stdout

def test_artifacts_root_behavior_matches_documented_scope():
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", "artifacts"], capture_output=True)
    assert result.returncode == 1
    assert b"Not ready for freeze" in result.stdout


# ═══════════════════════════════════════════════════════════════════════
# P3 — APLH v4.1 Final Closure integration tests
# ═══════════════════════════════════════════════════════════════════════

def test_validate_artifacts_examples_passes_under_documented_rules():
    """
    Pins the previously-reproduced gap: ``validate-artifacts`` run on
    ``artifacts/examples/minimal_demo_set`` must succeed exactly as
    documented in README.md CLI Usage section.

    Before v4.1, ``.aplh/freeze_gate_status.yaml`` was picked up by
    SchemaValidator and treated as an artifact — causing a spurious
    schema error.  The shared ``iter_artifact_yamls`` traversal now
    excludes ``.aplh/`` consistently, so this command must exit 0.
    """
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "aero_prop_logic_harness",
         "validate-artifacts", "--dir", "artifacts/examples/minimal_demo_set"],
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"validate-artifacts on examples should pass.  "
        f"stdout={result.stdout.decode()!r}  stderr={result.stderr.decode()!r}"
    )
    assert b"No schema validation issues" in result.stdout


def test_demo_graph_cannot_masquerade_as_freeze_complete(tmp_path):
    """
    Pins the most critical gap identified in final review: copying the
    demo graph to an arbitrary directory and changing its signoff to
    ``freeze-complete`` must NOT produce a formal freeze verdict.

    The formal boundary enforcement added in v4.1 verifies that
    ``freeze-complete`` scope is only accepted when the target
    directory resolves to the repository's ``artifacts/`` root.
    """
    import sys
    import shutil

    # Copy the full demo graph to a temporary location
    demo_src = Path("artifacts/examples/minimal_demo_set")
    demo_copy = tmp_path / "fake_formal"
    shutil.copytree(demo_src, demo_copy)

    # Tamper with signoff: claim freeze-complete
    signoff_path = demo_copy / ".aplh" / "freeze_gate_status.yaml"
    assert signoff_path.is_file(), "Demo set must include .aplh/freeze_gate_status.yaml"
    original = signoff_path.read_text()
    tampered = original.replace("demo-scale", "freeze-complete")
    signoff_path.write_text(tampered)

    # Run freeze-readiness against the tampered copy
    result = subprocess.run(
        [sys.executable, "-m", "aero_prop_logic_harness",
         "freeze-readiness", "--dir", str(demo_copy)],
        capture_output=True,
    )

    # Must fail
    assert result.returncode == 1, (
        f"Tampered demo graph must NOT pass freeze-readiness.  "
        f"stdout={result.stdout.decode()!r}"
    )
    # Error message must mention formal boundary violation
    assert b"Formal boundary violation" in result.stdout, (
        f"Output must explain formal boundary mismatch.  "
        f"stdout={result.stdout.decode()!r}"
    )
    assert b"formal baseline root" in result.stdout


def test_freeze_complete_only_allowed_for_formal_artifacts_root(tmp_path):
    """
    Direct positive/negative verification of the formal root binding:
    - A non-formal directory with ``freeze-complete`` → must fail.
    - The real ``artifacts/`` root (currently with ``freeze-complete``
      scope but incomplete signoff booleans) → must fail for other
      reasons, but NOT for formal boundary violation.
    """
    import sys

    # ── Negative: arbitrary tmp dir with freeze-complete ──────────────
    target = _create_minimal_passing_graph(tmp_path / "target")
    aplh = target / ".aplh"
    aplh.mkdir()
    (aplh / "freeze_gate_status.yaml").write_text(
        'baseline_scope: "freeze-complete"\n'
        'boundary_frozen: true\n'
        'schema_frozen: true\n'
        'trace_gate_passed: true\n'
        'baseline_review_complete: true\n'
        'signed_off_by: "X"\n'
        'signed_off_at: "2026-04-03T12:00:00Z"\n'
    )
    result = subprocess.run(
        [sys.executable, "-m", "aero_prop_logic_harness",
         "freeze-readiness", "--dir", str(target)],
        capture_output=True,
    )
    assert result.returncode == 1
    assert b"Formal boundary violation" in result.stdout

    # ── Positive: real artifacts/ root ────────────────────────────────
    # The real artifacts/ root claims freeze-complete but has incomplete
    # booleans, so it should fail — but NOT because of boundary violation.
    result2 = subprocess.run(
        [sys.executable, "-m", "aero_prop_logic_harness",
         "freeze-readiness", "--dir", "artifacts"],
        capture_output=True,
    )
    assert result2.returncode == 1
    # Must NOT fail due to formal boundary (it IS the formal root)
    assert b"Formal boundary violation" not in result2.stdout
