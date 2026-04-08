"""
Phase 2A model, schema, loader, and boundary tests.

This test module covers:
  - New artifact models (MODE, TRANS, GUARD) — positive & negative
  - GUARD.predicate grammar (AtomicPredicate, CompoundPredicate) — positive & negative
  - Additive fields backward compatibility on P0/P1 models
  - Trace extension (new directions accepted, boundaries enforced)
  - Loader/registry integration for new types
  - Frozen boundary decisions (no TRANS↔FUNC, no TRANS↔IFACE trace)
  - P0/P1 demo-scale regression
"""

import pytest
from pathlib import Path
from pydantic import ValidationError

from aero_prop_logic_harness.models import (
    Mode,
    Transition,
    Guard,
    AtomicPredicate,
    CompoundPredicate,
    PredicateOperator,
    PredicateCombinator,
    InputSignalRef,
    Requirement,
    Function,
    Interface,
    Abnormal,
    TraceLink,
    TraceLinkType,
    ArtifactType,
)
from aero_prop_logic_harness.loaders.artifact_loader import load_artifact
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry


# ═══════════════════════════════════════════════════════════════════════
# §1 — MODE model tests
# ═══════════════════════════════════════════════════════════════════════

class TestModeModel:
    """Tests for the Mode artifact model (§4.1)."""

    def test_valid_mode_minimal(self):
        m = Mode(id="MODE-0001", name="Normal Operation", mode_type="normal")
        assert m.artifact_type == ArtifactType.MODE
        assert m.mode_type == "normal"
        assert m.incoming_transitions == []
        assert m.outgoing_transitions == []

    def test_valid_mode_full(self):
        m = Mode(
            id="MODE-0002",
            name="Emergency",
            mode_type="emergency",
            description="Engine emergency shutdown mode",
            parent_mode="MODE-0001",
            is_initial=False,
            entry_conditions=["Fire detected", "Catastrophic failure"],
            exit_conditions=["Manual override by crew"],
            active_functions=["FUNC-0001"],
            monitored_interfaces=["IFACE-0001"],
            related_requirements=["REQ-0001"],
            related_abnormals=["ABN-0001"],
            incoming_transitions=["TRANS-0001"],
            outgoing_transitions=["TRANS-0002"],
        )
        assert m.id == "MODE-0002"
        assert len(m.incoming_transitions) == 1
        assert len(m.outgoing_transitions) == 1

    def test_invalid_mode_type_rejected(self):
        with pytest.raises(ValidationError, match="Invalid mode_type"):
            Mode(id="MODE-0003", name="Bad", mode_type="invalid_type")

    def test_all_valid_mode_types(self):
        for mt in ("normal", "degraded", "emergency", "startup", "shutdown", "test"):
            m = Mode(id="MODE-0001", name="T", mode_type=mt)
            assert m.mode_type == mt

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Mode(id="MODE-0001", name="T", mode_type="normal", bogus_field="x")

    def test_wrong_id_prefix_rejected(self):
        with pytest.raises(ValidationError):
            Mode(id="XXXX-0001", name="T", mode_type="normal")


# ═══════════════════════════════════════════════════════════════════════
# §2 — TRANSITION model tests
# ═══════════════════════════════════════════════════════════════════════

class TestTransitionModel:
    """Tests for the Transition artifact model (§4.2)."""

    def test_valid_transition_minimal(self):
        t = Transition(
            id="TRANS-0001",
            name="NormalToEmergency",
            source_mode="MODE-0001",
            target_mode="MODE-0002",
        )
        assert t.artifact_type == ArtifactType.TRANSITION
        assert t.guard == ""
        assert t.priority == 100
        assert t.actions == []

    def test_valid_transition_full(self):
        t = Transition(
            id="TRANS-0002",
            name="EmergencyToNormal",
            description="Recovery from emergency",
            source_mode="MODE-0002",
            target_mode="MODE-0001",
            trigger_signal="IFACE-0001.fire_clear",
            guard="GUARD-0001",
            priority=10,
            actions=["FUNC-0001", "FUNC-0002"],
            is_reversible=True,
            related_requirements=["REQ-0001"],
            related_abnormals=["ABN-0001"],
        )
        assert t.priority == 10
        assert len(t.actions) == 2

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Transition(
                id="TRANS-0001", name="T",
                source_mode="MODE-0001", target_mode="MODE-0002",
                bogus="x",
            )

    def test_negative_priority_rejected(self):
        with pytest.raises(ValidationError):
            Transition(
                id="TRANS-0001", name="T",
                source_mode="MODE-0001", target_mode="MODE-0002",
                priority=-1,
            )


# ═══════════════════════════════════════════════════════════════════════
# §3 — GUARD model + predicate grammar tests
# ═══════════════════════════════════════════════════════════════════════

class TestPredicateGrammar:
    """Tests for the GUARD.predicate grammar (§4.9)."""

    def test_atomic_gt(self):
        ap = AtomicPredicate(
            operator="gt", signal_ref="IFACE-0001.n2_speed",
            threshold=95.0, unit="%",
        )
        assert ap.predicate_type == "atomic"
        assert ap.operator == PredicateOperator.GT

    def test_atomic_bool_true(self):
        ap = AtomicPredicate(
            operator="bool_true", signal_ref="IFACE-0002.fire_detected",
        )
        assert ap.threshold is None

    def test_atomic_bool_with_threshold_rejected(self):
        with pytest.raises(ValidationError, match="must have null threshold"):
            AtomicPredicate(
                operator="bool_true", signal_ref="IFACE-0001.x",
                threshold=1.0,
            )

    def test_atomic_comparison_without_threshold_rejected(self):
        with pytest.raises(ValidationError, match="requires a non-null threshold"):
            AtomicPredicate(
                operator="gt", signal_ref="IFACE-0001.x",
            )

    def test_atomic_invalid_signal_ref_rejected(self):
        with pytest.raises(ValidationError, match="Invalid signal_ref"):
            AtomicPredicate(
                operator="gt", signal_ref="not_a_valid_ref",
                threshold=10.0,
            )

    def test_atomic_signal_ref_no_dot_rejected(self):
        with pytest.raises(ValidationError, match="Invalid signal_ref"):
            AtomicPredicate(
                operator="gt", signal_ref="IFACE-0001",
                threshold=10.0,
            )

    def test_compound_and(self):
        cp = CompoundPredicate(
            combinator="and",
            operands=[
                {"predicate_type": "atomic", "operator": "gt",
                 "signal_ref": "IFACE-0001.a", "threshold": 10.0},
                {"predicate_type": "atomic", "operator": "lt",
                 "signal_ref": "IFACE-0001.b", "threshold": 20.0},
            ],
        )
        assert len(cp.operands) == 2
        assert cp.combinator == PredicateCombinator.AND

    def test_compound_not_exactly_one_operand(self):
        cp = CompoundPredicate(
            combinator="not",
            operands=[
                {"predicate_type": "atomic", "operator": "bool_true",
                 "signal_ref": "IFACE-0001.x"},
            ],
        )
        assert len(cp.operands) == 1

    def test_compound_not_two_operands_rejected(self):
        with pytest.raises(ValidationError, match="NOT combinator requires exactly 1"):
            CompoundPredicate(
                combinator="not",
                operands=[
                    {"predicate_type": "atomic", "operator": "bool_true",
                     "signal_ref": "IFACE-0001.x"},
                    {"predicate_type": "atomic", "operator": "bool_true",
                     "signal_ref": "IFACE-0001.y"},
                ],
            )

    def test_compound_and_one_operand_rejected(self):
        with pytest.raises(ValidationError, match="requires at least 2 operands"):
            CompoundPredicate(
                combinator="and",
                operands=[
                    {"predicate_type": "atomic", "operator": "gt",
                     "signal_ref": "IFACE-0001.a", "threshold": 1.0},
                ],
            )

    def test_compound_nested(self):
        """Nested compound: AND(atomic, OR(atomic, atomic))"""
        cp = CompoundPredicate(
            combinator="and",
            operands=[
                {"predicate_type": "atomic", "operator": "gt",
                 "signal_ref": "IFACE-0001.a", "threshold": 10.0},
                {"predicate_type": "compound", "combinator": "or", "operands": [
                    {"predicate_type": "atomic", "operator": "lt",
                     "signal_ref": "IFACE-0001.b", "threshold": 5.0},
                    {"predicate_type": "atomic", "operator": "bool_true",
                     "signal_ref": "IFACE-0002.c"},
                ]},
            ],
        )
        assert isinstance(cp.operands[1], CompoundPredicate)

    def test_extra_fields_in_atomic_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AtomicPredicate(
                operator="gt", signal_ref="IFACE-0001.x",
                threshold=1.0, bogus="y",
            )


class TestGuardModel:
    """Tests for the Guard artifact model (§4.3)."""

    def test_valid_guard_atomic(self):
        g = Guard(
            id="GUARD-0001",
            name="Overspeed Guard",
            description="Activates when N2 exceeds 95%",
            predicate={
                "predicate_type": "atomic",
                "operator": "gt",
                "signal_ref": "IFACE-0001.n2_speed",
                "threshold": 95.0,
                "unit": "%",
            },
        )
        assert g.artifact_type == ArtifactType.GUARD
        assert isinstance(g.predicate, AtomicPredicate)
        assert g.used_by_transitions == []

    def test_valid_guard_compound(self):
        g = Guard(
            id="GUARD-0002",
            name="Multi-signal Guard",
            predicate={
                "predicate_type": "compound",
                "combinator": "and",
                "operands": [
                    {"predicate_type": "atomic", "operator": "gt",
                     "signal_ref": "IFACE-0001.n2_speed", "threshold": 95.0},
                    {"predicate_type": "atomic", "operator": "lt",
                     "signal_ref": "IFACE-0002.oil_pressure", "threshold": 20.0},
                ],
            },
            used_by_transitions=["TRANS-0001"],
            related_interfaces=["IFACE-0001", "IFACE-0002"],
        )
        assert isinstance(g.predicate, CompoundPredicate)
        assert len(g.used_by_transitions) == 1

    def test_guard_free_text_predicate_rejected(self):
        """Free-text string predicates must be rejected — must be structured object."""
        with pytest.raises(ValidationError):
            Guard(
                id="GUARD-0003",
                name="Bad",
                predicate="N2 > 95%",  # type: ignore
            )

    def test_guard_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Guard(
                id="GUARD-0001",
                name="T",
                predicate={
                    "predicate_type": "atomic",
                    "operator": "gt",
                    "signal_ref": "IFACE-0001.x",
                    "threshold": 1.0,
                },
                bogus="x",
            )

    def test_input_signal_ref_model(self):
        ref = InputSignalRef(interface="IFACE-0001", signal="n2_speed", unit="%")
        assert ref.interface == "IFACE-0001"


# ═══════════════════════════════════════════════════════════════════════
# §4 — Additive fields backward compatibility
# ═══════════════════════════════════════════════════════════════════════

class TestAdditiveFieldsBackwardCompat:
    """Verify P0/P1 models still load without new fields (§2.6)."""

    def test_requirement_without_new_fields(self):
        r = Requirement(
            id="REQ-0001", title="T", description="D",
        )
        assert r.linked_modes == []
        assert r.linked_transitions == []
        assert r.linked_guards == []

    def test_requirement_with_new_fields(self):
        r = Requirement(
            id="REQ-0001", title="T", description="D",
            linked_modes=["MODE-0001"],
            linked_transitions=["TRANS-0001"],
            linked_guards=["GUARD-0001"],
        )
        assert r.linked_modes == ["MODE-0001"]

    def test_function_without_new_fields(self):
        f = Function(id="FUNC-0001", name="F", purpose="P")
        assert f.related_modes == []
        assert f.related_transitions == []

    def test_function_with_new_fields(self):
        f = Function(
            id="FUNC-0001", name="F", purpose="P",
            related_modes=["MODE-0001"],
            related_transitions=["TRANS-0001"],
        )
        assert f.related_modes == ["MODE-0001"]

    def test_interface_without_new_fields(self):
        i = Interface(id="IFACE-0001", name="I")
        assert i.related_modes == []
        assert i.related_guards == []

    def test_abnormal_without_new_fields(self):
        a = Abnormal(id="ABN-0001", name="A")
        assert a.related_modes == []
        assert a.related_transitions == []


# ═══════════════════════════════════════════════════════════════════════
# §5 — Trace extension tests
# ═══════════════════════════════════════════════════════════════════════

class TestTraceExtension:
    """Verify new trace directions are accepted, boundaries enforced."""

    # All 11 Phase 2A trace directions
    @pytest.mark.parametrize("src,tgt,link_type", [
        ("REQ-0001", "MODE-0001", "requires_mode"),
        ("REQ-0001", "TRANS-0001", "requires_transition"),
        ("REQ-0001", "GUARD-0001", "defines_condition"),
        ("ABN-0001", "MODE-0001", "triggers_mode"),
        ("ABN-0001", "TRANS-0001", "triggers_transition"),
        ("MODE-0001", "FUNC-0001", "activates"),
        ("MODE-0001", "IFACE-0001", "monitors"),
        ("TRANS-0001", "MODE-0001", "exits"),
        ("TRANS-0001", "MODE-0002", "enters"),
        ("TRANS-0001", "GUARD-0001", "guarded_by"),
        ("GUARD-0001", "IFACE-0001", "observes"),
    ])
    def test_new_trace_direction_accepted(self, src, tgt, link_type):
        t = TraceLink(
            id="TRACE-9999",
            source_id=src,
            target_id=tgt,
            link_type=link_type,
        )
        assert t.link_type.value == link_type

    # All 14 P0/P1 trace directions still work
    @pytest.mark.parametrize("src,tgt,link_type", [
        ("REQ-0001", "FUNC-0001", "implements"),
        ("REQ-0001", "IFACE-0001", "constrains"),
        ("REQ-0001", "IFACE-0001", "relates_to"),
        ("REQ-0001", "ABN-0001", "relates_to"),
        ("FUNC-0001", "REQ-0001", "satisfies"),
        ("IFACE-0001", "REQ-0001", "satisfies"),
        ("FUNC-0001", "IFACE-0001", "uses"),
        ("FUNC-0001", "ABN-0001", "relates_to"),
        ("FUNC-0001", "ABN-0001", "detects"),
        ("FUNC-0001", "ABN-0001", "mitigates"),
        ("ABN-0001", "FUNC-0001", "triggers"),
        ("ABN-0001", "FUNC-0001", "relates_to"),
        ("ABN-0001", "IFACE-0001", "affects"),
        ("ABN-0001", "IFACE-0001", "relates_to"),
    ])
    def test_existing_trace_direction_still_works(self, src, tgt, link_type):
        t = TraceLink(
            id="TRACE-9999",
            source_id=src,
            target_id=tgt,
            link_type=link_type,
        )
        assert t.source_id == src

    def test_trans_to_func_trace_rejected(self):
        """§4.8 frozen decision: no TRANS → FUNC trace direction."""
        with pytest.raises(ValidationError, match="Invalid trace semantic"):
            TraceLink(
                id="TRACE-9999",
                source_id="TRANS-0001",
                target_id="FUNC-0001",
                link_type="activates",
            )

    def test_trans_to_iface_trace_rejected(self):
        """§4.6 frozen decision: no TRANS → IFACE trace direction."""
        with pytest.raises(ValidationError, match="Invalid trace semantic"):
            TraceLink(
                id="TRACE-9999",
                source_id="TRANS-0001",
                target_id="IFACE-0001",
                link_type="monitors",
            )

    def test_func_to_trans_trace_rejected(self):
        """No FUNC → TRANS trace direction exists."""
        with pytest.raises(ValidationError, match="Invalid trace semantic"):
            TraceLink(
                id="TRACE-9999",
                source_id="FUNC-0001",
                target_id="TRANS-0001",
                link_type="relates_to",
            )


# ═══════════════════════════════════════════════════════════════════════
# §6 — Loader / Registry integration
# ═══════════════════════════════════════════════════════════════════════

class TestLoaderIntegration:
    """Verify loader and registry can handle new artifact types."""

    def _write_mode_yaml(self, tmp_path):
        modes_dir = tmp_path / "modes"
        modes_dir.mkdir()
        mode_file = modes_dir / "mode-0001.yaml"
        mode_file.write_text(
            'id: "MODE-0001"\n'
            'artifact_type: "mode"\n'
            'name: "Normal"\n'
            'mode_type: "normal"\n'
            'status: "draft"\n'
            'review_status: "draft"\n'
            'provenance:\n'
            '  source_type: "human_authored"\n'
            '  method: "manual"\n'
            '  confidence: 1.0\n'
        )
        return mode_file

    def _write_transition_yaml(self, tmp_path):
        trans_dir = tmp_path / "transitions"
        trans_dir.mkdir()
        trans_file = trans_dir / "trans-0001.yaml"
        trans_file.write_text(
            'id: "TRANS-0001"\n'
            'artifact_type: "transition"\n'
            'name: "NormalToEmergency"\n'
            'source_mode: "MODE-0001"\n'
            'target_mode: "MODE-0002"\n'
            'status: "draft"\n'
            'review_status: "draft"\n'
            'provenance:\n'
            '  source_type: "human_authored"\n'
            '  method: "manual"\n'
            '  confidence: 1.0\n'
        )
        return trans_file

    def _write_guard_yaml(self, tmp_path):
        guards_dir = tmp_path / "guards"
        guards_dir.mkdir()
        guard_file = guards_dir / "guard-0001.yaml"
        guard_file.write_text(
            'id: "GUARD-0001"\n'
            'artifact_type: "guard"\n'
            'name: "Overspeed"\n'
            'description: "N2 exceeds 95%"\n'
            'predicate:\n'
            '  predicate_type: "atomic"\n'
            '  operator: "gt"\n'
            '  signal_ref: "IFACE-0001.n2_speed"\n'
            '  threshold: 95.0\n'
            '  unit: "%"\n'
            'status: "draft"\n'
            'review_status: "draft"\n'
            'provenance:\n'
            '  source_type: "human_authored"\n'
            '  method: "manual"\n'
            '  confidence: 1.0\n'
        )
        return guard_file

    def test_mode_loads_from_yaml(self, tmp_path):
        mode_file = self._write_mode_yaml(tmp_path)
        artifact = load_artifact(mode_file)
        assert isinstance(artifact, Mode)
        assert artifact.id == "MODE-0001"

    def test_transition_loads_from_yaml(self, tmp_path):
        trans_file = self._write_transition_yaml(tmp_path)
        artifact = load_artifact(trans_file)
        assert isinstance(artifact, Transition)
        assert artifact.source_mode == "MODE-0001"

    def test_guard_loads_from_yaml(self, tmp_path):
        guard_file = self._write_guard_yaml(tmp_path)
        artifact = load_artifact(guard_file)
        assert isinstance(artifact, Guard)
        assert isinstance(artifact.predicate, AtomicPredicate)

    def test_registry_loads_new_types(self, tmp_path):
        self._write_mode_yaml(tmp_path)
        self._write_transition_yaml(tmp_path)
        self._write_guard_yaml(tmp_path)
        registry = ArtifactRegistry()
        registry.load_from_directory(tmp_path)
        assert registry.artifact_exists("MODE-0001")
        assert registry.artifact_exists("TRANS-0001")
        assert registry.artifact_exists("GUARD-0001")

    def test_mode_type_spoofing_rejected(self, tmp_path):
        modes_dir = tmp_path / "modes"
        modes_dir.mkdir()
        bad_file = modes_dir / "mode-0001.yaml"
        bad_file.write_text(
            'id: "MODE-0001"\n'
            'artifact_type: "requirement"\n'
            'name: "T"\n'
            'mode_type: "normal"\n'
        )
        with pytest.raises(ValueError, match="Type spoofing detected"):
            load_artifact(bad_file)

    def test_guard_compound_loads_from_yaml(self, tmp_path):
        guards_dir = tmp_path / "guards"
        guards_dir.mkdir()
        guard_file = guards_dir / "guard-0002.yaml"
        guard_file.write_text(
            'id: "GUARD-0002"\n'
            'artifact_type: "guard"\n'
            'name: "Compound Guard"\n'
            'predicate:\n'
            '  predicate_type: "compound"\n'
            '  combinator: "and"\n'
            '  operands:\n'
            '    - predicate_type: "atomic"\n'
            '      operator: "gt"\n'
            '      signal_ref: "IFACE-0001.n2_speed"\n'
            '      threshold: 95.0\n'
            '    - predicate_type: "atomic"\n'
            '      operator: "lt"\n'
            '      signal_ref: "IFACE-0002.oil_pressure"\n'
            '      threshold: 20.0\n'
            'status: "draft"\n'
            'review_status: "draft"\n'
            'provenance:\n'
            '  source_type: "human_authored"\n'
            '  method: "manual"\n'
            '  confidence: 1.0\n'
        )
        artifact = load_artifact(guard_file)
        assert isinstance(artifact.predicate, CompoundPredicate)
        assert len(artifact.predicate.operands) == 2


# ═══════════════════════════════════════════════════════════════════════
# §7 — P0/P1 demo-scale regression
# ═══════════════════════════════════════════════════════════════════════

class TestP0P1Regression:
    """Verify existing demo set is unaffected by Phase 2A changes."""

    DEMO_DIR = Path("artifacts/examples/minimal_demo_set")

    def test_demo_set_still_loads(self):
        if not self.DEMO_DIR.exists():
            pytest.skip("Demo set not found")
        registry = ArtifactRegistry()
        registry.load_from_directory(self.DEMO_DIR)
        # Must have loaded the same artifacts as before
        assert len(registry.artifacts) > 0
        assert len(registry.traces) > 0

    def test_demo_set_validate_artifacts_cli(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "aero_prop_logic_harness",
             "validate-artifacts", "--dir", str(self.DEMO_DIR)],
            capture_output=True,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════
# §8 — Field-only boundary tests
# ═══════════════════════════════════════════════════════════════════════

class TestFieldOnlyBoundaries:
    """Verify frozen field-only decisions are correctly enforced."""

    def test_transition_actions_is_field_only(self):
        """TRANS.actions stores FUNC IDs but no TRANS→FUNC trace direction exists."""
        t = Transition(
            id="TRANS-0001", name="T",
            source_mode="MODE-0001", target_mode="MODE-0002",
            actions=["FUNC-0001", "FUNC-0002"],
        )
        assert t.actions == ["FUNC-0001", "FUNC-0002"]
        # But creating a trace for this is impossible
        with pytest.raises(ValidationError, match="Invalid trace semantic"):
            TraceLink(
                id="TRACE-9999",
                source_id="TRANS-0001",
                target_id="FUNC-0001",
                link_type="activates",
            )

    def test_no_predicate_expression_field_exists(self):
        """§4.7 R3 freeze: predicate_expression must not exist as a Guard field."""
        g = Guard(
            id="GUARD-0001", name="T",
            predicate={"predicate_type": "atomic", "operator": "gt",
                       "signal_ref": "IFACE-0001.x", "threshold": 1.0},
        )
        assert not hasattr(g, "predicate_expression")
        # Attempting to pass predicate_expression should be rejected by extra=forbid
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Guard(
                id="GUARD-0001", name="T",
                predicate={"predicate_type": "atomic", "operator": "gt",
                            "signal_ref": "IFACE-0001.x", "threshold": 1.0},
                predicate_expression="N2 > 95%",  # type: ignore
            )


# ═══════════════════════════════════════════════════════════════════════
# §9 — ID pattern tests for new prefixes
# ═══════════════════════════════════════════════════════════════════════

class TestNewIdPatterns:
    """Verify ID_PATTERN accepts new prefixes."""

    @pytest.mark.parametrize("valid_id", [
        "MODE-0001", "MODE-9999",
        "TRANS-0001", "TRANS-9999",
        "GUARD-0001", "GUARD-9999",
    ])
    def test_new_prefixes_accepted(self, valid_id):
        from aero_prop_logic_harness.models.common import validate_artifact_id
        assert validate_artifact_id(valid_id) == valid_id

    @pytest.mark.parametrize("invalid_id", [
        "MODE-1", "TRANS-12345", "GUARD-", "MODE0001",
    ])
    def test_malformed_new_ids_rejected(self, invalid_id):
        from aero_prop_logic_harness.models.common import validate_artifact_id
        with pytest.raises(ValueError, match="Invalid artifact ID"):
            validate_artifact_id(invalid_id)
