"""
core/retrieval/query_expander.py
================================
Rule-based query expansion — NO LLM calls (C1 compliant).

Maintains a hard-coded synonym / alias table targeting aerospace /
CFD engineering terminology in Chinese and English.

Usage::

    expander = QueryExpander()
    augmented_query, extra_tokens = expander.expand("飞机失速特性分析")
    # augmented_query: "飞机失速特性分析 stall"
    # extra_tokens: ["stall"]
"""
from __future__ import annotations

import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Aerospace & CFD terminology synonym table
# Format: trigger_pattern -> [synonyms_to_add]
# ---------------------------------------------------------------------------

_SYNONYM_TABLE: List[Tuple[str, List[str]]] = [
    # Aerodynamics
    (r"失速|stall", ["失速", "stall", "CLmax"]),
    (r"配平|trim", ["配平", "trim", "trimmed flight"]),
    (r"升降舵|elevator", ["升降舵", "elevator", "pitch control"]),
    (r"副翼|aileron", ["副翼", "aileron", "roll control"]),
    (r"方向舵|rudder", ["方向舵", "rudder", "yaw control"]),
    (r"升力系数|lift coefficient|CL\b", ["升力系数", "lift coefficient", "CL"]),
    (r"阻力系数|drag coefficient|CD\b", ["阻力系数", "drag coefficient", "CD"]),
    (r"俯仰力矩|pitching moment|Cm\b", ["俯仰力矩", "pitching moment", "Cm"]),
    (r"迎角|攻角|angle of attack|AoA|alpha\b", ["迎角", "攻角", "angle of attack", "AoA", "alpha"]),
    (r"马赫数|Mach", ["马赫数", "Mach number", "Ma"]),
    (r"雷诺数|Reynolds", ["雷诺数", "Reynolds number", "Re"]),
    (r"边界层|boundary layer", ["边界层", "boundary layer", "BL"]),
    (r"湍流|turbulence|turbulent", ["湍流", "turbulence", "turbulent flow"]),
    (r"层流|laminar", ["层流", "laminar flow"]),
    (r"分离|separation|detachment", ["分离", "flow separation", "separation bubble"]),
    (r"激波|shock wave|shock", ["激波", "shock wave", "normal shock", "oblique shock"]),
    (r"跨声速|transonic", ["跨声速", "transonic", "transonic regime"]),
    (r"超声速|supersonic", ["超声速", "supersonic"]),
    (r"亚声速|subsonic", ["亚声速", "subsonic"]),
    # CFD-specific
    (r"网格|mesh|grid", ["网格", "mesh", "grid", "structured grid", "unstructured mesh"]),
    (r"湍流模型|turbulence model", ["湍流模型", "turbulence model", "RANS", "SST", "k-omega", "k-epsilon"]),
    (r"收敛|convergence|converge", ["收敛", "convergence", "residual convergence"]),
    (r"残差|residual", ["残差", "residual", "convergence residual"]),
    (r"压力系数|Cp\b|pressure coefficient", ["压力系数", "Cp", "pressure coefficient"]),
    (r"表面压力|surface pressure", ["表面压力", "surface pressure", "wall pressure"]),
    (r"翼型|airfoil|aerofoil", ["翼型", "airfoil", "aerofoil", "wing section"]),
    (r"机翼|wing", ["机翼", "wing", "lifting surface"]),
    (r"扭矩|torque|moment", ["扭矩", "torque", "aerodynamic moment"]),
    # COMAC / aircraft type
    (r"C919|ARJ21|C929", ["C919", "narrow-body", "COMAC"]),
    (r"飞行包线|flight envelope", ["飞行包线", "flight envelope", "V-n diagram"]),
    (r"稳定性|stability", ["稳定性", "stability", "static stability", "dynamic stability"]),
    (r"操纵性|controllability|handling", ["操纵性", "controllability", "handling qualities"]),
    (r"颤振|flutter", ["颤振", "flutter", "aeroelastic flutter"]),
    (r"疲劳|fatigue", ["疲劳", "fatigue", "cyclic loading"]),
]


class QueryExpander:
    """
    Matches query tokens against the synonym table and returns an augmented
    query string plus a flat list of extra tokens for BM25 queries.
    """

    def expand(self, query: str) -> Tuple[str, List[str]]:
        """
        Parameters
        ----------
        query:
            Original user query.

        Returns
        -------
        augmented_query:
            Original query + space-joined synonyms appended (dedup'd).
        extra_tokens:
            Flat list of added synonym tokens (for direct BM25 injection).
        """
        added: List[str] = []
        for pattern, synonyms in _SYNONYM_TABLE:
            if re.search(pattern, query, re.IGNORECASE):
                for syn in synonyms:
                    # Don't add terms already present in the query
                    if syn.lower() not in query.lower():
                        added.append(syn)

        # Deduplicate while preserving order
        seen = set()
        deduped: List[str] = []
        for t in added:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        if deduped:
            augmented = query + " " + " ".join(deduped)
        else:
            augmented = query

        return augmented, deduped
