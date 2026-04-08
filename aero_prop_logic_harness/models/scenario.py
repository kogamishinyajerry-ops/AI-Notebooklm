from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

class ScenarioTick(BaseModel):
    """A single time tick in a scenario."""
    model_config = ConfigDict(extra="forbid")
    
    tick_id: int = Field(description="Sequential tick integer ID")
    signal_updates: Dict[str, Any] = Field(
        default_factory=dict,
        description="Updates to signal values applied at this tick. Keys must be 'IFACE-NNNN.signal_name'."
    )
    notes: Optional[str] = Field(default=None, description="Optional description of this tick's events")

class Scenario(BaseModel):
    """Demo-scale scenario definition.

    Phase 3-2 additions (all Optional for backward compatibility):
      - version: scenario version string
      - expected_final_mode: predicted end-state MODE ID for regression checks
      - expected_transitions: predicted transition IDs for regression checks
    """
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(description="Unique identifier for the scenario")
    title: str = Field(description="Human-readable title")
    description: Optional[str] = Field(default=None, description="Detailed description")
    baseline_scope: str = Field(
        default="demo-scale",
        description="Scope this scenario applies to. Must be 'demo-scale'."
    )
    initial_mode_id: str = Field(description="MODE ID to start the scenario in")
    ticks: List[ScenarioTick] = Field(description="Ordered list of ticks driving the scenario")
    tags: List[str] = Field(default_factory=list, description="Optional tags")
    # Phase 3-2 optional fields (backward compatible)
    version: Optional[str] = Field(default=None, description="Scenario version string")
    expected_final_mode: Optional[str] = Field(
        default=None,
        description="Expected final MODE ID after execution (for regression checks)"
    )
    expected_transitions: Optional[List[str]] = Field(
        default=None,
        description="Expected transition IDs triggered during execution"
    )
