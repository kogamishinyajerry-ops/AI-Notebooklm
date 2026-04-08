"""
Scenario structural pre-check (Phase 3-2).

Validates a Scenario against a ModeGraph *before* execution.
This is a **structural** validator only — it does not execute the
scenario or evaluate guard predicates.

Per PHASE3_ARCHITECTURE_PLAN §6.1.2, checks:
  SV-1  initial_mode_id exists in ModeGraph
  SV-2  signal_updates keys match IFACE-NNNN.signal_name pattern
  SV-3  tick_id values are strictly increasing
  SV-4  baseline_scope is 'demo-scale'
  SV-5  no empty ticks (signal_updates empty AND notes empty) — advisory
  SV-6  expected_final_mode (if present) exists in ModeGraph
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from aero_prop_logic_harness.models.scenario import Scenario
from aero_prop_logic_harness.services.mode_graph import ModeGraph

# Same pattern used in predicate.py for consistency
SIGNAL_REF_PATTERN = re.compile(r"^IFACE-[0-9]{4}\.\w+$")


@dataclass
class ValidationIssue:
    """A single validation finding."""
    check_id: str        # e.g., "SV-1"
    severity: str        # "error" | "warning"
    message: str
    tick_id: Optional[int] = None


@dataclass
class ScenarioValidationResult:
    """Aggregated result of scenario validation."""
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if no error-level issues exist."""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_report(self) -> str:
        """Human-readable validation report."""
        if not self.issues:
            return "Scenario validation passed — no issues found."
        lines = [f"Scenario validation: {self.error_count} error(s), {self.warning_count} warning(s)"]
        for issue in self.issues:
            tick_part = f" (tick {issue.tick_id})" if issue.tick_id is not None else ""
            lines.append(f"  [{issue.check_id}] {issue.severity.upper()}{tick_part}: {issue.message}")
        return "\n".join(lines)


class ScenarioValidator:
    """Structural pre-check for Scenario files against a ModeGraph.

    Does NOT execute the scenario or evaluate guards.
    """

    def __init__(self, graph: ModeGraph) -> None:
        self.graph = graph

    def validate(self, scenario: Scenario) -> ScenarioValidationResult:
        """Run all structural checks and return the result."""
        result = ScenarioValidationResult()

        self._check_sv1_initial_mode(scenario, result)
        self._check_sv2_signal_refs(scenario, result)
        self._check_sv3_tick_ordering(scenario, result)
        self._check_sv4_baseline_scope(scenario, result)
        self._check_sv5_empty_ticks(scenario, result)
        self._check_sv6_expected_final_mode(scenario, result)

        return result

    # ── Individual checks ─────────────────────────────────────────────

    def _check_sv1_initial_mode(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-1: initial_mode_id must exist in ModeGraph."""
        if scenario.initial_mode_id not in self.graph.nodes:
            result.issues.append(ValidationIssue(
                check_id="SV-1",
                severity="error",
                message=(
                    f"initial_mode_id '{scenario.initial_mode_id}' "
                    f"not found in ModeGraph (available: "
                    f"{sorted(self.graph.nodes.keys())})"
                ),
            ))

    def _check_sv2_signal_refs(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-2: signal_updates keys must match IFACE-NNNN.signal_name."""
        for tick in scenario.ticks:
            for key in tick.signal_updates:
                if not SIGNAL_REF_PATTERN.match(key):
                    result.issues.append(ValidationIssue(
                        check_id="SV-2",
                        severity="error",
                        message=(
                            f"Invalid signal reference '{key}'. "
                            f"Must match IFACE-NNNN.signal_name"
                        ),
                        tick_id=tick.tick_id,
                    ))

    def _check_sv3_tick_ordering(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-3: tick_id values must be strictly increasing."""
        if len(scenario.ticks) < 2:
            return
        for i in range(1, len(scenario.ticks)):
            prev_id = scenario.ticks[i - 1].tick_id
            curr_id = scenario.ticks[i].tick_id
            if curr_id <= prev_id:
                result.issues.append(ValidationIssue(
                    check_id="SV-3",
                    severity="error",
                    message=(
                        f"tick_id {curr_id} is not strictly greater than "
                        f"previous tick_id {prev_id}"
                    ),
                    tick_id=curr_id,
                ))

    def _check_sv4_baseline_scope(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-4: baseline_scope must be 'demo-scale'."""
        if scenario.baseline_scope != "demo-scale":
            result.issues.append(ValidationIssue(
                check_id="SV-4",
                severity="error",
                message=(
                    f"baseline_scope must be 'demo-scale', "
                    f"got '{scenario.baseline_scope}'"
                ),
            ))

    def _check_sv5_empty_ticks(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-5: Advisory warning for ticks with no signal_updates and no notes."""
        for tick in scenario.ticks:
            if not tick.signal_updates and not tick.notes:
                result.issues.append(ValidationIssue(
                    check_id="SV-5",
                    severity="warning",
                    message="Empty tick — no signal_updates and no notes",
                    tick_id=tick.tick_id,
                ))

    def _check_sv6_expected_final_mode(
        self, scenario: Scenario, result: ScenarioValidationResult
    ) -> None:
        """SV-6: If expected_final_mode is present, it must exist in ModeGraph."""
        expected = getattr(scenario, "expected_final_mode", None)
        if expected is not None and expected not in self.graph.nodes:
            result.issues.append(ValidationIssue(
                check_id="SV-6",
                severity="error",
                message=(
                    f"expected_final_mode '{expected}' "
                    f"not found in ModeGraph"
                ),
            ))
