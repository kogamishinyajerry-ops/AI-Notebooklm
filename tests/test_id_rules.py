import pytest

from aero_prop_logic_harness.models.common import validate_artifact_id, get_id_prefix

def test_valid_ids():
    valid_ids = [
        "REQ-0001",
        "FUNC-9999",
        "IFACE-0123",
        "ABN-0000",
        "TERM-0042",
        "TRACE-1234",
    ]
    for vid in valid_ids:
        assert validate_artifact_id(vid) == vid

def test_invalid_ids():
    invalid_ids = [
        "REQ-1",       # Not padded
        "func-0001",   # Lowercase prefix
        "REQ_0001",    # Wrong separator
        "REQ-00012",   # Too long
        "FOO-0001",    # Invalid prefix
        "REQ-ABCD",    # Not digits
    ]
    for iid in invalid_ids:
        with pytest.raises(ValueError):
            validate_artifact_id(iid)

def test_get_prefix():
    assert get_id_prefix("REQ-0001") == "REQ"
    assert get_id_prefix("FUNC-9999") == "FUNC"
