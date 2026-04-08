import pytest
from pydantic import ValidationError

from aero_prop_logic_harness.models import Requirement, ProvenanceSourceType

def test_valid_requirement():
    req = Requirement(
        id="REQ-0001",
        title="Test Requirements",
        description="A requirement description",
    )
    assert req.id == "REQ-0001"
    assert req.artifact_type.value == "requirement"
    assert req.provenance.source_type == ProvenanceSourceType.HUMAN_AUTHORED

def test_missing_required_fields():
    with pytest.raises(ValidationError):
        Requirement(id="REQ-0001", title="Test") # missing description
        
def test_invalid_confidence():
    with pytest.raises(ValidationError):
        Requirement(
            id="REQ-0002",
            title="T",
            description="D",
            provenance={"source_type": "human_authored", "confidence": 1.5} # Invalid confidence
        )
