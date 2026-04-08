"""
Phase 2B tests.

Covers:
  - ConsistencyValidator reverse-loop extension (MODE/TRANS/GUARD + additive fields)
  - ModeGraph read-only topology
  - ModeValidator static issue production
  - CoverageValidator ABN/degraded/emergency checks
  - validate-modes CLI three-scope directory contract
  - P2B-F5 checklist 7-heading structural gate
  - Signoff path rules
"""

from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path

import pytest

from aero_prop_logic_harness.models import (
    ArtifactType,
    Mode,
    Transition,
    Guard,
    Requirement,
    Function,
    Interface,
    Abnormal,
    TraceLink,
    TraceLinkType,
    AtomicPredicate,
    CompoundPredicate,
    PredicateCombinator,
    PredicateOperator,
    Provenance,
    ProvenanceSourceType,
    ReviewStatus,
    InputSignalRef,
)
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.services.mode_graph import ModeGraph
from aero_prop_logic_harness.validators.consistency_validator import (
    ConsistencyValidator,
)
from aero_prop_logic_harness.validators.mode_validator import ModeValidator
from aero_prop_logic_harness.validators.coverage_validator import CoverageValidator


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

_NOW = "2026-04-04T00:00:00Z"
_PROV = Provenance(
    source_type=ProvenanceSourceType.HUMAN_AUTHORED,
    confidence=0.9,
    reviewed_by="test",
    review_date="2026-04-04",
)


def _mode(mid: str, *, mode_type: str = "normal", is_initial: bool = False,
           active_funcs=None, monitored_ifaces=None, related_reqs=None,
           related_abns=None, incoming=None, outgoing=None) -> Mode:
    return Mode(
        id=mid, name=mid, mode_type=mode_type, is_initial=is_initial,
        active_functions=active_funcs or [],
        monitored_interfaces=monitored_ifaces or [],
        related_requirements=related_reqs or [],
        related_abnormals=related_abns or [],
        incoming_transitions=incoming or [],
        outgoing_transitions=outgoing or [],
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _trans(tid: str, *, src: str, tgt: str, guard: str = "",
           actions=None, related_reqs=None, related_abns=None,
           priority: int = 100, notes: str = "") -> Transition:
    return Transition(
        id=tid, name=tid, source_mode=src, target_mode=tgt,
        guard=guard, actions=actions or [], priority=priority,
        related_requirements=related_reqs or [],
        related_abnormals=related_abns or [],
        notes=notes,
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _guard(gid: str, *, iface_id: str = "IFACE-0001",
           signal: str = "n2_speed", op=PredicateOperator.GT,
           threshold=95.0, related_ifaces=None, related_reqs=None,
           used_by=None) -> Guard:
    return Guard(
        id=gid, name=gid,
        predicate=AtomicPredicate(
            operator=op,
            signal_ref=f"{iface_id}.{signal}",
            threshold=threshold,
        ),
        related_interfaces=related_ifaces or [iface_id],
        related_requirements=related_reqs or [],
        used_by_transitions=used_by or [],
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _req(rid: str, *, linked_funcs=None, linked_ifaces=None,
         linked_abns=None, linked_modes=None, linked_trans=None,
         linked_guards=None) -> Requirement:
    return Requirement(
        id=rid, title=rid, description="test",
        linked_functions=linked_funcs or [],
        linked_interfaces=linked_ifaces or [],
        linked_abnormals=linked_abns or [],
        linked_modes=linked_modes or [],
        linked_transitions=linked_trans or [],
        linked_guards=linked_guards or [],
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _func(fid: str, *, dep_reqs=None, rel_ifaces=None,
          abn_considerations=None, rel_modes=None) -> Function:
    return Function(
        id=fid, name=fid, purpose="test",
        dependent_requirements=dep_reqs or [],
        related_interfaces=rel_ifaces or [],
        abnormal_considerations=abn_considerations or [],
        related_modes=rel_modes or [],
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _iface(iid: str, *, related_reqs=None, related_funcs=None,
           related_abns=None, related_modes=None, related_guards=None,
           signals=None) -> Interface:
    return Interface(
        id=iid, name=iid,
        related_requirements=related_reqs or [],
        related_functions=related_funcs or [],
        related_abnormals=related_abns or [],
        related_modes=related_modes or [],
        related_guards=related_guards or [],
        signals=signals or [],
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _abn(aid: str, *, related_reqs=None, related_funcs=None,
         related_ifaces=None, related_modes=None, related_trans=None,
         severity: str = "") -> Abnormal:
    return Abnormal(
        id=aid, name=aid,
        related_requirements=related_reqs or [],
        related_functions=related_funcs or [],
        related_interfaces=related_ifaces or [],
        related_modes=related_modes or [],
        related_transitions=related_trans or [],
        severity_hint=severity,
        provenance=_PROV, review_status=ReviewStatus.REVIEWED,
        created_at=_NOW, updated_at=_NOW,
    )


def _trace(tid: str, src: str, tgt: str, lt: TraceLinkType) -> TraceLink:
    return TraceLink(
        id=tid, source_id=src, target_id=tgt, link_type=lt,
        created_at=_NOW,
    )


def _make_registry(*items) -> ArtifactRegistry:
    reg = ArtifactRegistry()
    for item in items:
        reg._add_item(item)
    return reg


# ════════════════════════════════════════════════════════════════════════
# 1. ConsistencyValidator extension tests
# ════════════════════════════════════════════════════════════════════════

class TestConsistencyExtension:
    """Verify that _get_all_embedded_links covers all 2B fields."""

    def test_mode_links_extracted(self):
        """MODE fields enter consistency scope."""
        m = _mode("MODE-0001", active_funcs=["FUNC-0001"],
                   monitored_ifaces=["IFACE-0001"],
                   related_reqs=["REQ-0001"],
                   related_abns=["ABN-0001"],
                   incoming=["TRANS-0001"],
                   outgoing=["TRANS-0002"])
        reg = _make_registry(m)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(m)
        assert "FUNC-0001" in links
        assert "IFACE-0001" in links
        assert "REQ-0001" in links
        assert "ABN-0001" in links
        assert "TRANS-0001" in links
        assert "TRANS-0002" in links

    def test_transition_links_extracted(self):
        """TRANS fields enter consistency scope (actions excluded per §4.8)."""
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002",
                   guard="GUARD-0001", actions=["FUNC-0001"],
                   related_reqs=["REQ-0001"],
                   related_abns=["ABN-0001"])
        reg = _make_registry(t)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(t)
        assert "MODE-0001" in links
        assert "MODE-0002" in links
        assert "GUARD-0001" in links
        assert "REQ-0001" in links
        assert "ABN-0001" in links
        # actions NOT in consistency scope
        assert "FUNC-0001" not in links

    def test_guard_links_extracted(self):
        """GUARD fields enter consistency scope."""
        g = _guard("GUARD-0001", related_ifaces=["IFACE-0001"],
                   related_reqs=["REQ-0001"],
                   used_by=["TRANS-0001"])
        reg = _make_registry(g)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(g)
        assert "IFACE-0001" in links
        assert "REQ-0001" in links
        assert "TRANS-0001" in links

    def test_requirement_additive_fields(self):
        """REQ additive fields (linked_modes/transitions/guards) extracted."""
        r = _req("REQ-0001", linked_modes=["MODE-0001"],
                 linked_trans=["TRANS-0001"],
                 linked_guards=["GUARD-0001"])
        reg = _make_registry(r)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(r)
        assert "MODE-0001" in links
        assert "TRANS-0001" in links
        assert "GUARD-0001" in links

    def test_function_additive_related_modes(self):
        """FUNC.related_modes extracted, FUNC.related_transitions NOT (§4.8)."""
        f = _func("FUNC-0001", rel_modes=["MODE-0001"])
        f.related_transitions = ["TRANS-0001"]  # field-only, NOT in scope
        reg = _make_registry(f)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(f)
        assert "MODE-0001" in links
        assert "TRANS-0001" not in links

    def test_interface_additive_fields(self):
        """IFACE additive fields extracted."""
        i = _iface("IFACE-0001", related_modes=["MODE-0001"],
                   related_guards=["GUARD-0001"])
        reg = _make_registry(i)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(i)
        assert "MODE-0001" in links
        assert "GUARD-0001" in links

    def test_abnormal_additive_fields(self):
        """ABN additive fields extracted."""
        a = _abn("ABN-0001", related_modes=["MODE-0001"],
                 related_trans=["TRANS-0001"])
        reg = _make_registry(a)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(a)
        assert "MODE-0001" in links
        assert "TRANS-0001" in links

    def test_transition_empty_guard_not_extracted(self):
        """Empty guard string must not be extracted."""
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002", guard="")
        reg = _make_registry(t)
        cv = ConsistencyValidator(reg)
        links = cv._get_all_embedded_links(t)
        assert "" not in links


# ════════════════════════════════════════════════════════════════════════
# 2. ModeGraph tests
# ════════════════════════════════════════════════════════════════════════

class TestModeGraph:
    """Read-only mode graph topology tests."""

    def _minimal_graph(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"])
        m2 = _mode("MODE-0002", incoming=["TRANS-0001"],
                    outgoing=["TRANS-0002"])
        m3 = _mode("MODE-0003", mode_type="shutdown",
                    incoming=["TRANS-0002"])
        t1 = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        t2 = _trans("TRANS-0002", src="MODE-0002", tgt="MODE-0003")
        g1 = _guard("GUARD-0001", used_by=["TRANS-0001"])
        reg = _make_registry(m1, m2, m3, t1, t2, g1)
        return ModeGraph.from_registry(reg), reg

    def test_basic_construction(self):
        graph, _ = self._minimal_graph()
        assert graph.mode_count == 3
        assert graph.transition_count == 2
        assert graph.guard_count == 1
        assert graph.initial_mode == "MODE-0001"

    def test_transitions_from(self):
        graph, _ = self._minimal_graph()
        assert graph.transitions_from("MODE-0001") == ["TRANS-0001"]
        assert graph.transitions_from("MODE-0003") == []

    def test_transitions_to(self):
        graph, _ = self._minimal_graph()
        assert graph.transitions_to("MODE-0002") == ["TRANS-0001"]

    def test_reachable_from(self):
        graph, _ = self._minimal_graph()
        reachable = graph.reachable_from("MODE-0001")
        assert reachable == {"MODE-0001", "MODE-0002", "MODE-0003"}

    def test_unreachable_modes_all_reachable(self):
        graph, _ = self._minimal_graph()
        assert graph.unreachable_modes() == []

    def test_unreachable_modes_with_island(self):
        m1 = _mode("MODE-0001", is_initial=True)
        m2 = _mode("MODE-0002")  # no transitions reach it
        reg = _make_registry(m1, m2)
        graph = ModeGraph.from_registry(reg)
        assert graph.unreachable_modes() == ["MODE-0002"]

    def test_dead_transitions(self):
        # Transition whose source_mode doesn't exist
        t1 = _trans("TRANS-0001", src="MODE-9999", tgt="MODE-0001")
        m1 = _mode("MODE-0001", is_initial=True)
        reg = _make_registry(m1, t1)
        graph = ModeGraph.from_registry(reg)
        assert graph.dead_transitions() == ["TRANS-0001"]

    def test_no_initial_mode(self):
        m1 = _mode("MODE-0001")
        reg = _make_registry(m1)
        graph = ModeGraph.from_registry(reg)
        assert graph.initial_mode is None
        # All modes unreachable
        assert graph.unreachable_modes() == ["MODE-0001"]


# ════════════════════════════════════════════════════════════════════════
# 3. ModeValidator tests
# ════════════════════════════════════════════════════════════════════════

class TestModeValidator:
    """Static mode validator issue production tests."""

    def test_no_initial_mode(self):
        m1 = _mode("MODE-0001")
        reg = _make_registry(m1)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "no_initial_mode" in types

    def test_multiple_initial_modes(self):
        m1 = _mode("MODE-0001", is_initial=True)
        m2 = _mode("MODE-0002", is_initial=True)
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "multiple_initial_modes" in types

    def test_valid_simple_graph(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"])
        m2 = _mode("MODE-0002", mode_type="shutdown",
                    incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        ok = mv.validate_all()
        assert ok, mv.get_report()

    def test_invalid_source_mode(self):
        m1 = _mode("MODE-0001", is_initial=True)
        t = _trans("TRANS-0001", src="MODE-9999", tgt="MODE-0001")
        reg = _make_registry(m1, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "invalid_source_mode" in types

    def test_invalid_guard_ref(self):
        m1 = _mode("MODE-0001", is_initial=True)
        m2 = _mode("MODE-0002", mode_type="shutdown",
                    incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002",
                   guard="GUARD-9999")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "invalid_guard_ref" in types

    def test_self_loop_without_notes(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"], incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0001", notes="")
        reg = _make_registry(m1, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "self_loop_missing_notes" in types

    def test_self_loop_with_notes_ok(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"], incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0001",
                   notes="Periodic self-check transition")
        reg = _make_registry(m1, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "self_loop_missing_notes" not in types

    def test_dead_end_non_terminal(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"])
        # Normal mode with no outgoing = dead end
        m2 = _mode("MODE-0002", incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "dead_end_non_terminal" in types

    def test_dead_end_shutdown_ok(self):
        m1 = _mode("MODE-0001", is_initial=True, outgoing=["TRANS-0001"])
        m2 = _mode("MODE-0002", mode_type="shutdown",
                    incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "dead_end_non_terminal" not in types

    def test_priority_conflict_advisory(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001", "TRANS-0002"])
        m2 = _mode("MODE-0002", mode_type="shutdown",
                    incoming=["TRANS-0001", "TRANS-0002"])
        t1 = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002",
                    priority=50)
        t2 = _trans("TRANS-0002", src="MODE-0001", tgt="MODE-0002",
                    priority=50)
        reg = _make_registry(m1, m2, t1, t2)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        advisories = [i for i in mv.issues if i.tier == "T3"]
        assert any(i.issue_type == "priority_conflict" for i in advisories)

    def test_action_func_missing(self):
        m1 = _mode("MODE-0001", is_initial=True, outgoing=["TRANS-0001"])
        m2 = _mode("MODE-0002", mode_type="shutdown",
                    incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002",
                   actions=["FUNC-9999"])
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        mv = ModeValidator(reg, graph)
        mv.validate_all()
        types = [i.issue_type for i in mv.issues]
        assert "action_func_missing" in types


# ════════════════════════════════════════════════════════════════════════
# 4. CoverageValidator tests
# ════════════════════════════════════════════════════════════════════════

class TestCoverageValidator:
    """Coverage and completeness check tests."""

    def test_abn_not_covered(self):
        m1 = _mode("MODE-0001", is_initial=True)
        a1 = _abn("ABN-0001")  # not referenced by any MODE/TRANS
        reg = _make_registry(m1, a1)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        types = [i.issue_type for i in cv.issues]
        assert "abn_not_covered" in types

    def test_abn_covered_by_mode(self):
        a1 = _abn("ABN-0001")
        m1 = _mode("MODE-0001", is_initial=True,
                    related_abns=["ABN-0001"])
        reg = _make_registry(m1, a1)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        types = [i.issue_type for i in cv.issues]
        assert "abn_not_covered" not in types

    def test_degraded_no_outgoing(self):
        m1 = _mode("MODE-0001", is_initial=True, outgoing=["TRANS-0001"])
        m2 = _mode("MODE-0002", mode_type="degraded",
                    incoming=["TRANS-0001"])
        t = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        reg = _make_registry(m1, m2, t)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        types = [i.issue_type for i in cv.issues]
        assert "degraded_no_outgoing" in types

    def test_degraded_with_recovery(self):
        m1 = _mode("MODE-0001", is_initial=True,
                    outgoing=["TRANS-0001"], incoming=["TRANS-0002"])
        m2 = _mode("MODE-0002", mode_type="degraded",
                    incoming=["TRANS-0001"], outgoing=["TRANS-0002"])
        t1 = _trans("TRANS-0001", src="MODE-0001", tgt="MODE-0002")
        t2 = _trans("TRANS-0002", src="MODE-0002", tgt="MODE-0001")
        reg = _make_registry(m1, m2, t1, t2)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        types = [i.issue_type for i in cv.issues]
        assert "degraded_no_outgoing" not in types
        # T2: recovery path exists
        assert "degraded_no_recovery" not in [i.issue_type for i in cv.issues]

    def test_emergency_not_reachable(self):
        m1 = _mode("MODE-0001", is_initial=True)
        m2 = _mode("MODE-0002", mode_type="emergency")  # no incoming
        reg = _make_registry(m1, m2)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        types = [i.issue_type for i in cv.issues]
        assert "emergency_not_reachable" in types

    def test_severity_mode_mismatch_advisory(self):
        a1 = _abn("ABN-0001", severity="catastrophic")
        m1 = _mode("MODE-0001", is_initial=True,
                    related_abns=["ABN-0001"])
        reg = _make_registry(m1, a1)
        graph = ModeGraph.from_registry(reg)
        cv = CoverageValidator(reg, graph)
        cv.validate_all()
        advisories = [i for i in cv.issues if i.tier == "T3"]
        assert any(i.issue_type == "severity_mode_mismatch" for i in advisories)


# ════════════════════════════════════════════════════════════════════════
# 5. P2B-F5: 7-heading structural gate
# ════════════════════════════════════════════════════════════════════════

class TestChecklistStructuralGate:
    """P2B-F5: verify docs/phase2b_review_checklist.md has all 7 headings."""

    REQUIRED_HEADINGS = [
        "# APLH Phase 2B Human Review Checklist",
        "## 1. Scope",
        "## 2. Review Items",
        "### 2.1 P2-C4-R",
        "### 2.2 P2-D4-R",
        "### 2.3 P2-D2-R",
        "## 3. Signoff",
    ]

    def test_checklist_exists(self):
        checklist_path = Path(__file__).parent.parent / "docs" / "phase2b_review_checklist.md"
        assert checklist_path.is_file(), f"Missing: {checklist_path}"

    def test_checklist_has_all_7_headings(self):
        checklist_path = Path(__file__).parent.parent / "docs" / "phase2b_review_checklist.md"
        content = checklist_path.read_text()
        headings = re.findall(r'^#{1,3} .+', content, re.MULTILINE)

        for required in self.REQUIRED_HEADINGS:
            found = any(h.startswith(required) for h in headings)
            assert found, (
                f"Missing required heading prefix: '{required}'\n"
                f"Found headings: {headings}"
            )

    def test_checklist_with_missing_heading_would_fail(self):
        """Negative test: a 5-heading subset would fail the 7-heading gate."""
        incomplete = textwrap.dedent("""\
            # APLH Phase 2B Human Review Checklist
            ## 1. Scope
            ## 2. Review Items
            ### 2.1 P2-C4-R
            ## 3. Signoff
        """)
        headings = re.findall(r'^#{1,3} .+', incomplete, re.MULTILINE)
        missing = []
        for req in self.REQUIRED_HEADINGS:
            if not any(h.startswith(req) for h in headings):
                missing.append(req)
        # Expect 2 missing: ### 2.2 P2-D4-R and ### 2.3 P2-D2-R
        assert len(missing) == 2
        assert "### 2.2 P2-D4-R" in missing
        assert "### 2.3 P2-D2-R" in missing


# ════════════════════════════════════════════════════════════════════════
# 6. Signoff path rules
# ════════════════════════════════════════════════════════════════════════

class TestSignoffPathRules:
    """Baseline-local signoff path validation."""

    def test_formal_aplh_dir_exists(self):
        aplh_dir = Path(__file__).parent.parent / "artifacts" / ".aplh"
        assert aplh_dir.is_dir(), f"Missing formal .aplh: {aplh_dir}"

    def test_demo_aplh_dir_exists(self):
        aplh_dir = (
            Path(__file__).parent.parent
            / "artifacts" / "examples" / "minimal_demo_set" / ".aplh"
        )
        assert aplh_dir.is_dir(), f"Missing demo .aplh: {aplh_dir}"

    def test_formal_freeze_gate_status(self):
        gate = (
            Path(__file__).parent.parent
            / "artifacts" / ".aplh" / "freeze_gate_status.yaml"
        )
        assert gate.is_file()

    def test_demo_freeze_gate_status(self):
        gate = (
            Path(__file__).parent.parent
            / "artifacts" / "examples" / "minimal_demo_set"
            / ".aplh" / "freeze_gate_status.yaml"
        )
        assert gate.is_file()


# ════════════════════════════════════════════════════════════════════════
# 7. validate-modes CLI integration tests
# ════════════════════════════════════════════════════════════════════════

class TestValidateModesCLI:
    """CLI three-scope directory contract tests using subprocess."""

    def test_formal_root_exit_0(self):
        """validate-modes --dir artifacts/ should exit 0 (zero Phase 2 artifacts)."""
        import sys, subprocess
        result = subprocess.run(
            [sys.executable, "-m", "aero_prop_logic_harness", "validate-modes",
             "--dir", "artifacts"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "[Formal]" in result.stdout

    def test_demo_root_exit_0(self):
        """validate-modes --dir artifacts/examples/minimal_demo_set/ should exit 0."""
        import sys, subprocess
        result = subprocess.run(
            [sys.executable, "-m", "aero_prop_logic_harness", "validate-modes",
             "--dir", "artifacts/examples/minimal_demo_set"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "[Demo-scale]" in result.stdout

    def test_unmanaged_dir_exit_0(self, tmp_path):
        """validate-modes --dir <empty tmp> should exit 0 with [Unmanaged]."""
        import sys, subprocess
        result = subprocess.run(
            [sys.executable, "-m", "aero_prop_logic_harness", "validate-modes",
             "--dir", str(tmp_path)],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "[Unmanaged]" in result.stdout

    def test_nonexistent_dir_exit_1(self):
        """validate-modes --dir /nonexistent should exit 1."""
        import sys, subprocess
        result = subprocess.run(
            [sys.executable, "-m", "aero_prop_logic_harness", "validate-modes",
             "--dir", "/tmp/aplh_nonexistent_dir_12345"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 1
