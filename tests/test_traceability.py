import pytest
from pydantic import ValidationError
from aero_prop_logic_harness.models import TraceLink

def test_valid_trace_link():
    trace = TraceLink(
        id="TRACE-0001",
        source_id="REQ-0001",
        target_id="FUNC-0001",
        link_type="implements"
    )
    assert trace.id == "TRACE-0001"

def test_invalid_trace_direction():
    with pytest.raises(ValidationError, match="Invalid trace semantic"):
        # REQ -> REQ is not allowed
        TraceLink(
            id="TRACE-0002",
            source_id="REQ-0001",
            target_id="REQ-0002",
            link_type="relates_to"
        )
