"""
core/knowledge/entity_whitelist.py
====================================
S-23 Gap-C: Domain-structured entity whitelist for COMAC NotebookLM.

Three domains are covered:
  1. CFD / Aerodynamics   — retained from S-23 baseline
  2. Airworthiness / Regs — expanded per Opus 4.6 Gap-C approval
  3. Aviation Safety       — expanded per Opus 4.6 Gap-C approval

All terms are static hard-coded strings (C1 compliant — zero runtime
network calls or external downloads).

Vocabulary references:
  - EASA CS-25 / FAA FAR Part 25 / CCAR-25 structure
  - arXiv:2604.13101 entity schema (used as vocabulary reference only;
    no code or model from that paper is imported)
  - COMAC C919/C929 engineering documentation conventions
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Domain 1: CFD / Aerodynamics
# ---------------------------------------------------------------------------
CFD_ENTITIES: frozenset[str] = frozenset({
    # Simulation methods
    "CFD", "RANS", "LES", "DNS", "DES", "URANS", "IDDES",
    "SST", "k-omega", "k-epsilon", "Spalart-Allmaras",
    "turbulence model", "turbulence modeling",
    # Flow physics
    "boundary layer", "turbulence", "laminar", "transition",
    "flow separation", "separation bubble", "reattachment",
    "shock wave", "normal shock", "oblique shock", "bow shock",
    "wake", "vortex", "tip vortex", "leading edge vortex",
    "stall", "deep stall", "buffet", "flutter",
    # Aero parameters
    "lift coefficient", "CL", "drag coefficient", "CD",
    "pitching moment", "Cm", "rolling moment", "Cl",
    "yawing moment", "Cn", "pressure coefficient", "Cp",
    "angle of attack", "AoA", "alpha",
    "sideslip angle", "beta",
    "Mach number", "Ma", "transonic", "subsonic", "supersonic", "hypersonic",
    "Reynolds number", "Re",
    # Aircraft geometry
    "airfoil", "aerofoil", "wing section", "NACA",
    "wing", "machine wing", "机翼", "翼型",
    "chord", "span", "aspect ratio", "sweep angle", "dihedral",
    "leading edge", "trailing edge", "camber", "thickness ratio",
    "winglet", "winglet tip", "blended winglet",
    # Control surfaces
    "elevator", "升降舵", "aileron", "副翼", "rudder", "方向舵",
    "flap", "slat", "spoiler", "trim", "配平",
    # CFD numerics
    "mesh", "grid", "structured grid", "unstructured mesh",
    "mesh convergence", "mesh refinement", "y-plus", "y+",
    "convergence", "residual", "CFL", "time step",
    "finite volume", "finite element", "finite difference",
    # Chinese aerospace terms (from S-23 baseline)
    "失速", "边界层", "湍流", "层流", "分离", "激波",
    "迎角", "攻角", "马赫数", "雷诺数", "升力系数", "阻力系数",
    "俯仰力矩", "压力系数", "表面压力", "收敛", "残差", "网格",
    "颤振", "疲劳", "稳定性", "操纵性",
    "发动机", "推力", "燃烧室", "涡扇",
    "C919", "C929", "ARJ21", "COMAC", "CAD", "CAE",
})

# ---------------------------------------------------------------------------
# Domain 2: Airworthiness / Certification
# ---------------------------------------------------------------------------
AIRWORTHINESS_ENTITIES: frozenset[str] = frozenset({
    # ── Weight & balance ──────────────────────────────────────────────────
    "MTOW", "MZFW", "MLW", "OEW", "payload", "zero fuel weight",
    "maximum takeoff weight", "maximum landing weight",
    "basic operating weight", "BOW",
    # ── Speeds ───────────────────────────────────────────────────────────
    "Vmo", "Mmo", "Vd", "Vc", "Va", "Vs", "Vs1g",
    "VMO", "MMO", "VD", "VC", "VA", "VS",
    "design cruising speed", "design dive speed",
    "stall speed", "maneuver speed", "never-exceed speed",
    "minimum control speed", "Vmc", "Vmca", "Vmcg",
    # ── Load categories ──────────────────────────────────────────────────
    "limit load", "ultimate load", "proof load",
    "gust load", "dynamic gust", "discrete gust",
    "maneuver load", "ground load", "landing load",
    "fatigue load", "spectrum load", "load spectrum",
    "cabin pressure load", "pressurisation load",
    "inertia load", "thermal load",
    # ── Safety factors ───────────────────────────────────────────────────
    "factor of safety", "safety factor", "1.5 factor",
    "fitting factor", "casting factor", "bearing factor",
    "scatter factor", "environmental factor",
    # ── Damage tolerance & fatigue ───────────────────────────────────────
    "damage tolerance", "damage tolerant", "fail-safe",
    "safe-life", "crack growth", "crack propagation",
    "residual strength", "fracture mechanics", "fracture toughness",
    "stress intensity factor", "SIF", "KIC", "KI",
    "inspection interval", "threshold inspection", "repeat inspection",
    "non-propagation threshold", "fatigue life",
    "Miner's rule", "S-N curve", "fatigue spectrum",
    # ── Structural components ────────────────────────────────────────────
    "wing spar", "front spar", "rear spar", "centre spar",
    "fuselage frame", "fuselage ring", "circumferential frame",
    "skin panel", "wing skin", "fuselage skin", "stringer",
    "rib", "spar cap", "shear web", "bulkhead",
    "longeron", "keel beam", "floor beam", "pressure bulkhead",
    "joint", "splice", "fastener", "rivet", "lug", "fitting",
    # ── Regulations / documents ──────────────────────────────────────────
    "Part 25", "FAR 25", "CS-25", "CCAR-25",
    "FAR", "EASA", "CAAC", "FAA", "TCCA",
    "Type Certificate", "TC", "STC", "supplemental type certificate",
    "Amended Type Certificate", "ATC",
    "AD", "airworthiness directive",
    "TCDS", "type certificate data sheet",
    "CofA", "Certificate of Airworthiness",
    "AMC", "acceptable means of compliance",
    "MOC", "means of compliance",
    "Special Condition", "SC", "exemption",
    "Issue Paper", "IP", "CRI",
    # FAR/CS Part 25 article references
    "§25.301", "§25.303", "§25.305", "§25.307",  # loads
    "§25.321", "§25.331", "§25.335",              # flight loads
    "§25.341", "§25.343", "§25.345",              # gust & maneuver
    "§25.365", "§25.371", "§25.391",              # pressurisation & inertia
    "§25.471", "§25.473", "§25.479", "§25.481",  # ground loads
    "§25.519", "§25.521",                          # jacking
    "§25.561", "§25.562",                          # emergency landing
    "§25.571", "§25.573",                          # damage tolerance
    "§25.601", "§25.603", "§25.605",              # general structure
    "§25.613",                                     # material properties
    "§25.629",                                     # flutter
    "§25.631",                                     # bird strike
    "25.301", "25.303", "25.305", "25.571", "25.573", "25.629",
    # ── Material / certification ─────────────────────────────────────────
    "design allowable", "A-basis", "B-basis", "S-basis",
    "material qualification", "material specification",
    "composite", "CFRP", "carbon fibre", "carbon fiber",
    "aluminium alloy", "titanium alloy",
    "coupon test", "element test", "sub-component test", "full-scale test",
    "building block approach", "test pyramid",
    # ── Structural analysis methods ──────────────────────────────────────
    "FEM", "FEA", "finite element model", "finite element analysis",
    "stress analysis", "strain", "deformation", "deflection",
    "margin of safety", "MOS", "interaction equation",
    "buckling", "column buckling", "panel buckling",
    "crippling", "inter-rivet buckling",
    # Chinese equivalents
    "适航", "型号合格证", "适航指令", "补充型号合格证",
    "极限载荷", "限制载荷", "安全系数", "损伤容限",
    "破损安全", "安全寿命", "裂纹扩展", "剩余强度",
    "疲劳分析", "疲劳寿命", "疲劳试验",
    "结构强度", "有限元", "应力分析", "屈曲",
})

# ---------------------------------------------------------------------------
# Domain 3: Aviation Safety
# ---------------------------------------------------------------------------
SAFETY_ENTITIES: frozenset[str] = frozenset({
    # ── Safety analysis methods ──────────────────────────────────────────
    "FMEA", "Failure Mode and Effects Analysis",
    "FMECA", "criticality analysis",
    "FTA", "Fault Tree Analysis", "fault tree",
    "PSSA", "preliminary system safety assessment",
    "SSA", "system safety assessment",
    "CCA", "common cause analysis",
    "ZSA", "zonal safety analysis",
    "PRA", "probabilistic risk assessment",
    "hazard analysis", "hazard identification",
    "risk assessment", "risk matrix",
    # ── Severity classifications ─────────────────────────────────────────
    "catastrophic", "hazardous", "major", "minor", "no safety effect",
    "DAL", "design assurance level",
    "DAL A", "DAL B", "DAL C", "DAL D", "DAL E",
    "probability", "probability per flight hour",
    "extremely improbable", "extremely remote", "remote", "probable",
    # ── Maintenance documentation ────────────────────────────────────────
    "MEL", "Minimum Equipment List",
    "CDL", "Configuration Deviation List",
    "AML", "Approved Maintenance List",
    "AMM", "Aircraft Maintenance Manual",
    "CMM", "Component Maintenance Manual",
    "SRM", "Structural Repair Manual",
    "IPC", "Illustrated Parts Catalog",
    # ── Maintenance programs ─────────────────────────────────────────────
    "MRBR", "Maintenance Review Board Report",
    "MSG-3", "Maintenance Steering Group",
    "MPD", "Maintenance Planning Document",
    "MRB", "Maintenance Review Board",
    "scheduled maintenance", "unscheduled maintenance",
    "maintenance interval", "check interval",
    "A-check", "B-check", "C-check", "D-check",
    "heavy maintenance", "line maintenance",
    # ── Inspection methods ───────────────────────────────────────────────
    "NDT", "Non-Destructive Testing",
    "NDI", "Non-Destructive Inspection",
    "DVI", "Detailed Visual Inspection",
    "GVI", "General Visual Inspection",
    "SDI", "Special Detailed Inspection",
    "FEC", "Functional and Environmental Check",
    "UT", "ultrasonic testing", "ultrasonic inspection",
    "ET", "eddy current testing", "eddy current",
    "RT", "radiographic testing", "X-ray inspection",
    "PT", "penetrant testing", "liquid penetrant",
    "MT", "magnetic particle testing",
    "thermography", "shearography",
    # ── Reliability / availability ───────────────────────────────────────
    "MTBF", "Mean Time Between Failures",
    "MTBUR", "Mean Time Between Unscheduled Removals",
    "MTTF", "Mean Time To Failure",
    "reliability", "availability", "dispatch reliability",
    "redundancy", "active redundancy", "standby redundancy",
    "single point of failure", "SPOF",
    # ── Certification / operational ──────────────────────────────────────
    "ETOPS", "extended operations",
    "RVSM", "reduced vertical separation minimum",
    "CATIII", "CAT III", "autoland",
    "take-off alternate", "destination alternate",
    "EDTO", "extended diversion time operations",
    # Chinese equivalents
    "失效模式", "故障树", "安全评估", "危害分析",
    "维修大纲", "无损检测", "超声检测", "涡流检测",
    "可靠性", "冗余设计", "单点失效",
    "最低设备清单", "构型偏差清单",
})

# ---------------------------------------------------------------------------
# Combined whitelist (flat frozenset — used by graph_extractor)
# ---------------------------------------------------------------------------
ENTITY_WHITELIST: frozenset[str] = (
    CFD_ENTITIES | AIRWORTHINESS_ENTITIES | SAFETY_ENTITIES
)

# ── Domain map (for diagnostics / future filtering) ───────────────────────
DOMAIN_MAP: dict[str, str] = {}
for _term in CFD_ENTITIES:
    DOMAIN_MAP[_term] = "cfd"
for _term in AIRWORTHINESS_ENTITIES:
    DOMAIN_MAP[_term] = "airworthiness"
for _term in SAFETY_ENTITIES:
    DOMAIN_MAP[_term] = "safety"
