"""
Mode Graph service (Phase 2B).

Builds a read-only directed graph from MODE/TRANS/GUARD artifacts
loaded into an ArtifactRegistry.  Provides topology queries needed
by mode_validator and coverage_validator.

Per PHASE2B_ARCHITECTURE_PLAN §6.1:
  - Pure data structure, read-only query interface.
  - No step() / fire() / execute() / evaluate() methods.
  - Not a state machine engine.
"""

from __future__ import annotations

from collections import defaultdict

from aero_prop_logic_harness.models import Mode, Transition, Guard
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry


class ModeGraph:
    """Read-only directed graph of MODE nodes, TRANS edges, and GUARD conditions.

    Constructed via ``ModeGraph.from_registry()``.  All query methods are
    pure read-only operations over the frozen snapshot.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, Mode] = {}            # MODE-xxxx -> Mode
        self.edges: dict[str, Transition] = {}       # TRANS-xxxx -> Transition
        self.guards: dict[str, Guard] = {}           # GUARD-xxxx -> Guard
        self.initial_mode: str | None = None         # MODE-xxxx with is_initial=True

        # Adjacency indices (computed at build time)
        self._outgoing: dict[str, list[str]] = defaultdict(list)  # mode_id -> [trans_id]
        self._incoming: dict[str, list[str]] = defaultdict(list)  # mode_id -> [trans_id]

    # -- Construction --------------------------------------------------------

    @classmethod
    def from_registry(cls, registry: ArtifactRegistry) -> "ModeGraph":
        """Build a ModeGraph from the artifacts currently in *registry*."""
        graph = cls()

        for art_id, art in registry.artifacts.items():
            if isinstance(art, Mode):
                graph.nodes[art_id] = art
                if art.is_initial:
                    graph.initial_mode = art_id
            elif isinstance(art, Transition):
                graph.edges[art_id] = art
            elif isinstance(art, Guard):
                graph.guards[art_id] = art

        # Build adjacency
        for trans_id, trans in graph.edges.items():
            graph._outgoing[trans.source_mode].append(trans_id)
            graph._incoming[trans.target_mode].append(trans_id)

        return graph

    # -- Read-only queries ---------------------------------------------------

    def transitions_from(self, mode_id: str) -> list[str]:
        """Return TRANS-xxxx IDs of transitions leaving *mode_id*."""
        return list(self._outgoing.get(mode_id, []))

    def transitions_to(self, mode_id: str) -> list[str]:
        """Return TRANS-xxxx IDs of transitions entering *mode_id*."""
        return list(self._incoming.get(mode_id, []))

    def reachable_from(self, mode_id: str) -> set[str]:
        """Return all MODE-xxxx IDs reachable from *mode_id* via outgoing transitions."""
        visited: set[str] = set()
        stack = [mode_id]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for trans_id in self._outgoing.get(current, []):
                target = self.edges[trans_id].target_mode
                if target not in visited:
                    stack.append(target)
        return visited

    def unreachable_modes(self) -> list[str]:
        """Return MODE-xxxx IDs not reachable from the initial mode.

        If no initial mode exists, returns all modes (they are
        trivially unreachable because no starting point is defined).
        """
        if not self.initial_mode or self.initial_mode not in self.nodes:
            return sorted(self.nodes.keys())

        reachable = self.reachable_from(self.initial_mode)
        return sorted(m for m in self.nodes if m not in reachable)

    def dead_transitions(self) -> list[str]:
        """Return TRANS-xxxx IDs whose source_mode is not a known MODE node."""
        return sorted(
            t_id for t_id, t in self.edges.items()
            if t.source_mode not in self.nodes
        )

    @property
    def mode_count(self) -> int:
        return len(self.nodes)

    @property
    def transition_count(self) -> int:
        return len(self.edges)

    @property
    def guard_count(self) -> int:
        return len(self.guards)
