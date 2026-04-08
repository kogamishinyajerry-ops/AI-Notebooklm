import pytest
from pydantic import ValidationError
import subprocess
from pathlib import Path
import json

from aero_prop_logic_harness.models import Requirement, TraceLink, ReviewStatus, TraceLinkType
from aero_prop_logic_harness.loaders.artifact_loader import load_artifact

def test_extra_fields_forbidden():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        req = Requirement(
            id="REQ-0001",
            title="T",
            description="D",
            fake_phase_2_field="sneaky"
        )
        
def test_trace_semantic_mismatch():
    with pytest.raises(ValidationError, match="Invalid trace semantic"):
        # REQ -> FUNC expects IMPLEMENTS, DETECTS is invalid
        TraceLink(
            id="TRACE-0001",
            source_id="REQ-0001",
            target_id="FUNC-0001",
            link_type=TraceLinkType.DETECTS
        )

def test_strict_dates():
    with pytest.raises(ValidationError, match="String should match pattern"):
        Requirement(
            id="REQ-0001",
            title="T",
            description="D",
            created_at="yesterday"
        )

def test_file_path_mismatch(tmp_path):
    # Create REQ file inside "functions" dir
    bad_dir = tmp_path / "functions"
    bad_dir.mkdir()
    bad_file = bad_dir / "req-9999.yaml"
    bad_file.write_text('''
id: "REQ-9999"
artifact_type: "requirement"
title: "T"
description: "D"
    ''')
    
    with pytest.raises(ValueError, match="Directory naming violation"):
        load_artifact(bad_file)
    
def test_freeze_readiness_cli_exit_codes():
    # Calling the CLI as a subprocess to check exit code on failure
    # If we pass a bad directory, it should exit(1)
    import sys
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", "nonexistent_dir"], capture_output=True)
    assert result.returncode == 1
    assert b"Not ready for freeze" in result.stdout

