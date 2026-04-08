from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class TransitionRecord(BaseModel):
    """Machine-readable record of a mode transition."""
    model_config = ConfigDict(extra="forbid")

    tick_id: int
    applied_signals: Dict[str, Any]
    mode_before: str
    candidates_considered: List[str]
    transition_selected: Optional[str] = None
    actions_emitted: List[str] = []
    mode_after: str
    block_reason: Optional[str] = None
    # Phase 3: audit correlation fields
    run_id: Optional[str] = None
    scenario_id: Optional[str] = None


class DecisionTrace:
    """Collects and formats the decision records.

    Phase 3 enhancement: carries session-level ``run_id`` and
    ``scenario_id`` for audit correlation across trace → signoff → replay.
    """
    def __init__(
        self,
        run_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        evaluator_mode: Optional[str] = None,
    ) -> None:
        self.records: List[TransitionRecord] = []
        self.run_id: Optional[str] = run_id
        self.scenario_id: Optional[str] = scenario_id
        self.evaluator_mode: Optional[str] = evaluator_mode

    def add_record(self, record: TransitionRecord) -> None:
        self.records.append(record)

    def to_human_readable(self) -> str:
        lines = ["=== Scenario Execution Trace ==="]
        if self.run_id:
            lines.append(f"Run ID:       {self.run_id}")
        if self.scenario_id:
            lines.append(f"Scenario ID:  {self.scenario_id}")
        if self.run_id or self.scenario_id:
            lines.append("───────────────────────────────")
        for rec in self.records:
            lines.append(f"Tick {rec.tick_id}:")
            lines.append(f"  Signals: {rec.applied_signals}")
            lines.append(f"  Mode Before: {rec.mode_before}")
            lines.append(f"  Candidates: {rec.candidates_considered}")
            if rec.block_reason:
                lines.append(f"  [BLOCKED] Reason: {rec.block_reason}")
            elif rec.transition_selected:
                lines.append(f"  Selected: {rec.transition_selected} -> Mode After: {rec.mode_after}")
                if rec.actions_emitted:
                    lines.append(f"  Emitted Actions: {rec.actions_emitted}")
            else:
                lines.append(f"  (No valid transition)")
        lines.append("================================")
        return "\n".join(lines)

    def to_machine_readable(self) -> Dict[str, Any]:
        """Return a structured dict suitable for YAML/JSON serialization."""
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "evaluator_mode": self.evaluator_mode,
            "records": [r.model_dump() for r in self.records],
        }
