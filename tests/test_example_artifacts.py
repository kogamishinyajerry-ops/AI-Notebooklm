from pathlib import Path
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.validators import TraceValidator, ConsistencyValidator

EXAMPLES_DIR = Path("artifacts/examples/minimal_demo_set")

import subprocess
import sys

def test_example_artifacts_load_and_validate():
    # Only run if directory exists to avoid failures when testing subset
    if not EXAMPLES_DIR.exists():
        return
        
    registry = ArtifactRegistry()
    registry.load_from_directory(EXAMPLES_DIR)
    
    # 1. No Orphan Pass
    orphans = [art_id for art_id in registry.artifacts if registry.is_orphan(art_id)]
    assert len(orphans) == 0, f"Examples must not have orphans: {orphans}"
    
    # 2. Relation Coverage Pass
    relations = {
        "REQ->FUNC": False,
        "REQ->IFACE": False,
        "REQ->ABN": False,
        "FUNC->IFACE": False,
        "ABN->FUNC_OR_IFACE": False,
    }
    for trace in registry.traces.values():
        src_prefix = trace.source_id.split("-")[0]
        tgt_prefix = trace.target_id.split("-")[0]
        if src_prefix == "REQ" and tgt_prefix == "FUNC": relations["REQ->FUNC"] = True
        elif src_prefix == "REQ" and tgt_prefix == "IFACE": relations["REQ->IFACE"] = True
        elif src_prefix == "REQ" and tgt_prefix == "ABN": relations["REQ->ABN"] = True
        elif src_prefix == "FUNC" and tgt_prefix == "IFACE": relations["FUNC->IFACE"] = True
        elif src_prefix == "ABN" and tgt_prefix in ("FUNC", "IFACE"): relations["ABN->FUNC_OR_IFACE"] = True
    assert all(relations.values()), f"Examples must have full relational topology. Missing: {[k for k, v in relations.items() if not v]}"
    
    # 3. Trace Reverse Loop Pass
    consist_val = ConsistencyValidator(registry)
    assert consist_val.validate_all() is True, f"Consistency (including reverse loops) should pass. Issues: {consist_val.issues}"

def test_examples_baseline_isolation():
    # 4. Baseline / Examples isolation pass when scanning artifacts root
    # Should yield Empty Graph Check exit code 1
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", "artifacts"], capture_output=True)
    assert result.returncode == 1
    assert b"Empty Graph Check: \xe2\x9d\x8c Fail (0 traces)" in result.stdout

def test_example_artifacts_respect_declared_scope():
    # Ensure that running freeze-readiness on examples gives the demo-scale warning, not freeze-complete
    result = subprocess.run([sys.executable, "-m", "aero_prop_logic_harness", "freeze-readiness", "--dir", str(EXAMPLES_DIR)], capture_output=True)
    if result.returncode == 0:
        assert b"Demo-scale gate checks passed (Not for formal freeze)" in result.stdout
        assert b"Ready for Formal Baseline Freeze" not in result.stdout
