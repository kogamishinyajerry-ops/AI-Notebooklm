"""
Coverage Validator (Phase 2B).

Static validator for ABN coverage, degraded-mode recovery paths,
and emergency-mode reachability.

Per PHASE2B_ARCHITECTURE_PLAN section 6.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from aero_prop_logic_harness.models import Mode, Transition, Abnormal
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph


@dataclass
class CoverageIssue:
    artifact_id: str
    issue_type: str
    message: str
    tier: str = "T1"  # T1 = blocking, T2 = manual signoff at 2C, T3 = advisory


class CoverageValidator:
    """Static coverage and completeness checks for the mode graph.

    All checks are read-only, issue-producing operations.
    No execution engine, no content generation, no evaluator.
    """

    def __init__(self, registry: ArtifactRegistry, graph: ModeGraph):
        self.registry = registry
        self.graph = graph
        self.issues: list[CoverageIssue] = []

    def validate_all(self) -> bool:
        """Run all coverage checks. Returns True if no T1 issues found."""
        self.issues.clear()

        self._check_abn_coverage()
        self._check_degraded_outgoing()
        self._check_degraded_recovery_path()
        self._check_emergency_reachable()
        self._check_abn_severity_alignment()

        return not any(i.tier == "T1" for i in self.issues)

    # -- P2-D1: every ABN referenced by at least one MODE or TRANS -----------

    def _check_abn_coverage(self) -> None:
        # Collect all ABN IDs referenced by any MODE.related_abnormals
        # or TRANS.related_abnormals
        referenced_abns: set[str] = set()
        for mode in self.graph.nodes.values():
            referenced_abns.update(mode.related_abnormals)
        for trans in self.graph.edges.values():
            referenced_abns.update(trans.related_abnormals)

        # Check every ABN artifact in registry
        for art_id, art in self.registry.artifacts.items():
            if isinstance(art, Abnormal):
                if art_id not in referenced_abns:
                    self.issues.append(CoverageIssue(
                        art_id, "abn_not_covered",
                        f"Abnormal {art_id} is not referenced by any "
                        f"MODE.related_abnormals or TRANS.related_abnormals.",
                    ))

    # -- P2-D2: degraded modes must have outgoing transitions ----------------

    def _check_degraded_outgoing(self) -> None:
        for mode_id, mode in self.graph.nodes.items():
            if mode.mode_type == "degraded":
                outgoing = self.graph.transitions_from(mode_id)
                if not outgoing:
                    self.issues.append(CoverageIssue(
                        mode_id, "degraded_no_outgoing",
                        f"Degraded mode {mode_id} has zero outgoing transitions "
                        f"(cannot recover or transition to other modes).",
                    ))

    # -- P2-D2-R: degraded recovery path (T2 manual signoff at 2C) ----------

    def _check_degraded_recovery_path(self) -> None:
        normal_modes = {
            m_id for m_id, m in self.graph.nodes.items()
            if m.mode_type == "normal"
        }
        for mode_id, mode in self.graph.nodes.items():
            if mode.mode_type != "degraded":
                continue
            # Check if any outgoing transition leads to a normal mode
            outgoing = self.graph.transitions_from(mode_id)
            leads_to_normal = False
            for trans_id in outgoing:
                trans = self.graph.edges[trans_id]
                if trans.target_mode in normal_modes:
                    leads_to_normal = True
                    break
            if not leads_to_normal and outgoing:
                self.issues.append(CoverageIssue(
                    mode_id, "degraded_no_recovery",
                    f"Degraded mode {mode_id} has outgoing transitions but "
                    f"none lead directly to a 'normal' mode. "
                    f"Requires manual review at Phase 2C.",
                    tier="T2",
                ))

    # -- P2-D3: emergency mode must be target of at least one transition -----

    def _check_emergency_reachable(self) -> None:
        for mode_id, mode in self.graph.nodes.items():
            if mode.mode_type == "emergency":
                incoming = self.graph.transitions_to(mode_id)
                if not incoming:
                    self.issues.append(CoverageIssue(
                        mode_id, "emergency_not_reachable",
                        f"Emergency mode {mode_id} is not the target of any transition.",
                    ))

    # -- P2-D4-R: ABN severity vs mode_type alignment (T3 advisory) ---------

    def _check_abn_severity_alignment(self) -> None:
        for mode_id, mode in self.graph.nodes.items():
            for abn_id in mode.related_abnormals:
                abn = self.registry.get_artifact(abn_id)
                if not isinstance(abn, Abnormal):
                    continue
                if not abn.severity_hint:
                    continue
                # Advisory: hazardous/catastrophic ABN should map to
                # emergency or degraded mode, not normal
                if abn.severity_hint in ("hazardous", "catastrophic"):
                    if mode.mode_type == "normal":
                        self.issues.append(CoverageIssue(
                            mode_id, "severity_mode_mismatch",
                            f"Mode {mode_id} (type=normal) references {abn_id} "
                            f"(severity={abn.severity_hint}). Expected degraded "
                            f"or emergency mode.",
                            tier="T3",
                        ))

    # -- Report --------------------------------------------------------------

    def get_report(self) -> str:
        if not self.issues:
            return "Coverage Validator: No issues found."
        t1 = [i for i in self.issues if i.tier == "T1"]
        t2 = [i for i in self.issues if i.tier == "T2"]
        t3 = [i for i in self.issues if i.tier == "T3"]
        lines = [
            f"Coverage Validator: {len(t1)} blocking + "
            f"{len(t2)} manual-review + {len(t3)} advisory issues:"
        ]
        for issue in self.issues:
            tag = f"[{issue.tier}]" if issue.tier != "T1" else ""
            lines.append(
                f"  - {tag}[{issue.issue_type}] {issue.artifact_id}: {issue.message}"
            )
        return "\n".join(lines)
