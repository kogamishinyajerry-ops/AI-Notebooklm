"""
Mode Validator (Phase 2B).

Static issue producer that consumes a ModeGraph and emits structural
validation issues.  Does NOT execute, evaluate, or simulate anything.

Per PHASE2B_ARCHITECTURE_PLAN section 6.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

from aero_prop_logic_harness.models import (
    Mode, Transition, Guard,
    AtomicPredicate, CompoundPredicate,
)
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph


@dataclass
class ModeValidationIssue:
    artifact_id: str
    issue_type: str
    message: str
    tier: str = "T1"  # T1 = blocking, T3 = advisory


class ModeValidator:
    """Static structural validator for MODE/TRANS/GUARD topology.

    All checks are read-only, issue-producing operations.
    No execution, no evaluation, no runtime arbitration.
    """

    def __init__(self, registry: ArtifactRegistry, graph: ModeGraph):
        self.registry = registry
        self.graph = graph
        self.issues: list[ModeValidationIssue] = []

    def validate_all(self) -> bool:
        """Run all structural checks and return True if no T1 issues found."""
        self.issues.clear()

        self._check_initial_mode()
        self._check_mode_reachability()
        self._check_transition_endpoints()
        self._check_guard_references()
        self._check_trigger_signal_iface()
        self._check_actions_func_existence()
        self._check_self_loops()
        self._check_unreachable_modes()
        self._check_dead_end_modes()
        self._check_orphan_transitions()
        self._check_priority_guard_conflicts()
        self._check_predicate_signal_refs()

        return not any(i.tier == "T1" for i in self.issues)

    # -- P2-B1: exactly one initial mode -------------------------------------

    def _check_initial_mode(self) -> None:
        initials = [m_id for m_id, m in self.graph.nodes.items() if m.is_initial]
        if len(initials) == 0:
            self.issues.append(ModeValidationIssue(
                "GRAPH", "no_initial_mode",
                "No MODE with is_initial=True found.",
            ))
        elif len(initials) > 1:
            self.issues.append(ModeValidationIssue(
                "GRAPH", "multiple_initial_modes",
                f"Multiple initial modes: {initials}. Exactly one required.",
            ))

    # -- P2-B2: all modes reachable from initial -----------------------------

    def _check_mode_reachability(self) -> None:
        unreachable = self.graph.unreachable_modes()
        for mode_id in unreachable:
            self.issues.append(ModeValidationIssue(
                mode_id, "unreachable_from_initial",
                f"Mode {mode_id} is not reachable from the initial mode.",
            ))

    # -- P2-B3: transition endpoint resolution -------------------------------

    def _check_transition_endpoints(self) -> None:
        for trans_id, trans in self.graph.edges.items():
            if trans.source_mode not in self.graph.nodes:
                self.issues.append(ModeValidationIssue(
                    trans_id, "invalid_source_mode",
                    f"source_mode '{trans.source_mode}' does not resolve to a known MODE.",
                ))
            if trans.target_mode not in self.graph.nodes:
                self.issues.append(ModeValidationIssue(
                    trans_id, "invalid_target_mode",
                    f"target_mode '{trans.target_mode}' does not resolve to a known MODE.",
                ))

    # -- P2-B5: guard reference resolution -----------------------------------

    def _check_guard_references(self) -> None:
        for trans_id, trans in self.graph.edges.items():
            if trans.guard and trans.guard not in self.graph.guards:
                self.issues.append(ModeValidationIssue(
                    trans_id, "invalid_guard_ref",
                    f"guard '{trans.guard}' does not resolve to a known GUARD.",
                ))

    # -- trigger_signal IFACE existence (structural, field-only per 4.6) -----

    def _check_trigger_signal_iface(self) -> None:
        for trans_id, trans in self.graph.edges.items():
            if trans.trigger_signal:
                # trigger_signal is a convenience label; extract IFACE-NNNN prefix
                iface_match = re.match(r"^(IFACE-\d{4})", trans.trigger_signal)
                if iface_match:
                    iface_id = iface_match.group(1)
                    if not self.registry.artifact_exists(iface_id):
                        self.issues.append(ModeValidationIssue(
                            trans_id, "trigger_signal_iface_missing",
                            f"trigger_signal references '{iface_id}' which does not exist.",
                        ))

    # -- actions FUNC existence (structural, field-only per 4.8) -------------

    def _check_actions_func_existence(self) -> None:
        for trans_id, trans in self.graph.edges.items():
            for func_id in trans.actions:
                if not self.registry.artifact_exists(func_id):
                    self.issues.append(ModeValidationIssue(
                        trans_id, "action_func_missing",
                        f"action references '{func_id}' which does not exist.",
                    ))

    # -- P2-B4: self-loop must have notes ------------------------------------

    def _check_self_loops(self) -> None:
        for trans_id, trans in self.graph.edges.items():
            if trans.source_mode == trans.target_mode:
                if not trans.notes or not trans.notes.strip():
                    self.issues.append(ModeValidationIssue(
                        trans_id, "self_loop_missing_notes",
                        f"Self-loop on {trans.source_mode} must have non-empty notes.",
                    ))

    # -- P2-C1: unreachable modes (non-initial with no incoming) -------------

    def _check_unreachable_modes(self) -> None:
        for mode_id, mode in self.graph.nodes.items():
            if mode.is_initial:
                continue
            if not self.graph.transitions_to(mode_id):
                self.issues.append(ModeValidationIssue(
                    mode_id, "no_incoming_transitions",
                    f"Non-initial mode {mode_id} has zero incoming transitions.",
                ))

    # -- P2-C2: dead-end modes must be shutdown or emergency -----------------

    def _check_dead_end_modes(self) -> None:
        for mode_id, mode in self.graph.nodes.items():
            if not self.graph.transitions_from(mode_id):
                if mode.mode_type not in ("shutdown", "emergency"):
                    self.issues.append(ModeValidationIssue(
                        mode_id, "dead_end_non_terminal",
                        f"Mode {mode_id} has zero outgoing transitions but "
                        f"mode_type is '{mode.mode_type}' (expected 'shutdown' or 'emergency').",
                    ))

    # -- P2-C3: orphan transitions (source mode unreachable) -----------------

    def _check_orphan_transitions(self) -> None:
        unreachable_set = set(self.graph.unreachable_modes())
        for trans_id, trans in self.graph.edges.items():
            if trans.source_mode in unreachable_set:
                self.issues.append(ModeValidationIssue(
                    trans_id, "orphan_transition",
                    f"Transition {trans_id} originates from unreachable mode {trans.source_mode}.",
                ))

    # -- P2-C4-R: priority + guard conflict (T3 advisory) --------------------

    def _check_priority_guard_conflicts(self) -> None:
        # Group transitions by source_mode
        from collections import defaultdict
        by_source: dict[str, list[Transition]] = defaultdict(list)
        for trans in self.graph.edges.values():
            by_source[trans.source_mode].append(trans)

        for source_mode, transitions in by_source.items():
            if len(transitions) < 2:
                continue
            # Check for same-priority transitions from the same source
            by_priority: dict[int, list[Transition]] = defaultdict(list)
            for t in transitions:
                by_priority[t.priority].append(t)

            for prio, group in by_priority.items():
                if len(group) > 1:
                    ids = [t.id for t in group]
                    self.issues.append(ModeValidationIssue(
                        source_mode, "priority_conflict",
                        f"Transitions {ids} from {source_mode} have identical "
                        f"priority {prio}. Check guard mutual exclusivity.",
                        tier="T3",
                    ))

    # -- Predicate signal_ref checks -----------------------------------------

    def _check_predicate_signal_refs(self) -> None:
        for guard_id, guard in self.graph.guards.items():
            signal_refs = self._collect_signal_refs(guard.predicate)
            declared_ifaces = set(guard.related_interfaces)

            for sig_ref in signal_refs:
                # sig_ref format: IFACE-NNNN.signal_name
                parts = sig_ref.split(".", 1)
                if len(parts) != 2:
                    continue
                iface_id, signal_name = parts

                # Check IFACE exists
                if not self.registry.artifact_exists(iface_id):
                    self.issues.append(ModeValidationIssue(
                        guard_id, "predicate_iface_missing",
                        f"predicate signal_ref '{sig_ref}' references "
                        f"non-existent interface {iface_id}.",
                    ))
                    continue

                # Check signal exists in interface
                iface = self.registry.get_artifact(iface_id)
                if iface and hasattr(iface, 'signals'):
                    sig_names = {s.name for s in iface.signals}
                    if signal_name not in sig_names:
                        self.issues.append(ModeValidationIssue(
                            guard_id, "predicate_signal_missing",
                            f"predicate signal_ref '{sig_ref}': signal '{signal_name}' "
                            f"not found in {iface_id}.signals.",
                        ))

                # Check coverage: referenced IFACE must be in related_interfaces
                if iface_id not in declared_ifaces:
                    self.issues.append(ModeValidationIssue(
                        guard_id, "predicate_iface_not_declared",
                        f"predicate references {iface_id} but it is not in "
                        f"guard.related_interfaces.",
                    ))

    def _collect_signal_refs(
        self, pred: Union[AtomicPredicate, CompoundPredicate]
    ) -> list[str]:
        """Recursively collect all signal_ref values from a predicate tree."""
        refs: list[str] = []
        if isinstance(pred, AtomicPredicate):
            refs.append(pred.signal_ref)
        elif isinstance(pred, CompoundPredicate):
            for operand in pred.operands:
                refs.extend(self._collect_signal_refs(operand))
        return refs

    # -- Report --------------------------------------------------------------

    def get_report(self) -> str:
        if not self.issues:
            return "Mode Validator: No issues found."
        t1 = [i for i in self.issues if i.tier == "T1"]
        t3 = [i for i in self.issues if i.tier == "T3"]
        lines = [f"Mode Validator: {len(t1)} blocking + {len(t3)} advisory issues:"]
        for issue in self.issues:
            tag = f"[{issue.tier}]" if issue.tier != "T1" else ""
            lines.append(
                f"  - {tag}[{issue.issue_type}] {issue.artifact_id}: {issue.message}"
            )
        return "\n".join(lines)
