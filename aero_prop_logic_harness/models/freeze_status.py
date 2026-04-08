"""
Freeze status model.

Represents the human sign-off state for a baseline freeze.
"""

from typing import Annotated
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, StrictBool, AwareDatetime

class BaselineScope(str, Enum):
    """Scope of the target baseline being evaluated."""
    DEMO_SCALE = "demo-scale"
    FREEZE_COMPLETE = "freeze-complete"

class FreezeGateStatus(BaseModel):
    """
    Machine-readable freeze signoff document.
    """
    model_config = ConfigDict(extra="forbid")
    
    baseline_scope: BaselineScope = Field(description="The formal intent of this baseline (demo-scale vs freeze-complete)")
    
    boundary_frozen: StrictBool = Field(description="Has boundary/scope been frozen?")
    schema_frozen: StrictBool = Field(description="Has the artifact schema been frozen?")
    trace_gate_passed: StrictBool = Field(description="Have traceability and relational semantics passed?")
    baseline_review_complete: StrictBool = Field(description="Has the human baseline review been completed?")
    
    signed_off_by: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Name or ID of the authorizing reviewer"
    )
    signed_off_at: AwareDatetime = Field(
        description="Strict timezone-aware datetime signature"
    )
