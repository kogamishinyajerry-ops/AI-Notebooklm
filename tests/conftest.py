"""
conftest.py — pytest session-level configuration for AI-Notebooklm test suite.

Ensures the synthetic retrieval corpus is regenerated in ChromaDB once
at the start of the session, before any tests run. This guarantees the
regression test sees a clean, reproducible corpus regardless of test
execution order (since other tests may mutate the shared ChromaDB state).
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# IMPORTANT: Import heavy ML modules HERE, before test_gap_a_retriever.py runs.
# test_gap_a_retriever checks "if _name not in sys.modules" before creating MagicMock stubs.
# If these are already in sys.modules (as REAL modules) when test_gap_a_retriever.py
# is collected, test_gap_a_retriever will NOT create stubs for them.
# This prevents C-extension re-import failures in eval_corpus_setup.
# IMPORTANT: Pre-import heavy ML modules HERE, before test_gap_a_retriever.py runs.
# test_gap_a_retriever checks "if _name not in sys.modules" before creating MagicMock stubs.
# NOTE: test_gap_a_retriever's _stub() unconditionally sets sys.modules[name] = mod
# (without checking if name is already there), so it OVERWRITES these pre-imports with
# MagicMock stubs. We cache the real modules to restore them in _restore_retrieval_modules.
# sentence_transformers is a Python package (not C-extension), so re-import is safe.
_real_sentence_transformers = None
_torch_mod = None
_transformers_mod = None
for _name in ("torch", "transformers", "sentence_transformers"):
    try:
        __import__(_name)
        _mod = sys.modules.get(_name)
        if _mod is not None and "MagicMock" not in type(_mod).__name__:
            if _name == "sentence_transformers":
                _real_sentence_transformers = _mod
            elif _name == "torch":
                _torch_mod = _mod
            elif _name == "transformers":
                _transformers_mod = _mod
    except ImportError:
        pass  # offline env may not have them; accept that case gracefully


@pytest.fixture(scope="session", autouse=False)
def eval_corpus_setup():
    """
    Session-scoped fixture that (1) undoes MagicMock stubs from test_gap_a_retriever.py
    and (2) regenerates the synthetic corpus — in the correct order.

    NOT autouse: only runs when explicitly requested by test modules that need
    the real ChromaDB-backed retrieval pipeline (e.g. test_retrieval_quality_regression.py).
    This keeps test_gap_a_retriever.py unaffected — its MagicMock stubs persist
    when that test file runs in isolation.

    test_gap_a_retriever.py patches sys.modules at IMPORT TIME with MagicMock
    stubs for chromadb, tenacity, sentence_transformers, torch, transformers,
    fitz, core.retrieval.embeddings, core.retrieval.vector_store, and
    core.retrieval.reranker.

    This fixture MUST run before any code tries to use the real ChromaDB or
    EmbeddingManager. It cleans ALL stubbed modules (including sentence_transformers)
    so that re-imported classes capture the real implementations at class-definition time.
    """
    # ------------------------------------------------------------------
    # Step 1: Detect and undo MagicMock stubs
    # ------------------------------------------------------------------
    chromadb_cached = sys.modules.get("chromadb")
    vs_cached = sys.modules.get("core.retrieval.vector_store")

    def _is_stub(mod, attr):
        val = getattr(mod, attr, None) if mod else None
        if val is None:
            return False
        t = type(val)
        if "MagicMock" in t.__name__:
            return True
        if isinstance(val, type) and "MagicMock" in val.__name__:
            return True
        return False

    chromadb_is_stub = _is_stub(chromadb_cached, "PersistentClient")
    vs_is_stub = _is_stub(vs_cached, "VectorStoreAdapter")

    # NOTE: chromadb_cached may be None if test_gap_a_retriever.py's module-level
    # cleanup deleted sys.modules["chromadb"] after conftest cached it at module-load time.
    # We treat None as "needs restoration" to cover this case too.
    if chromadb_is_stub or vs_is_stub or chromadb_cached is None:
        pass  # cleanup runs below

        keys_to_remove = []
        for key in list(sys.modules.keys()):
            if key == "chromadb" or key.startswith("chromadb."):
                keys_to_remove.append(key)
            elif key == "core.retrieval.vector_store" or key.startswith("core.retrieval.vector_store."):
                keys_to_remove.append(key)
            elif key == "core.retrieval.embeddings" or key.startswith("core.retrieval.embeddings."):
                keys_to_remove.append(key)
            elif key == "core.retrieval.reranker" or key.startswith("core.retrieval.reranker."):
                keys_to_remove.append(key)
            elif key == "tenacity" or key.startswith("tenacity."):
                keys_to_remove.append(key)
            elif key == "fitz":
                keys_to_remove.append(key)
            # NOTE: sentence_transformers, torch, and transformers are NOT added to
            # keys_to_remove. They were pre-imported at conftest module level BEFORE
            # test_gap_a_retriever.py ran, so _real_sentence_transformers holds the REAL
            # module. We restore them separately (see "CRITICAL: Restore REAL..." block
            # below) after the sys.modules deletion to ensure the re-imported core/retrieval
            # modules pick up the real SentenceTransformer (not MagicMock).

        for key in keys_to_remove:
            del sys.modules[key]

        # Re-import RAG-core modules that need restoration.
        # NOTE: Do NOT re-import torch, transformers, sentence_transformers, or fitz here.
        # They are the REAL modules (imported at conftest module level before
        # test_gap_a_retriever.py ran). Re-importing C-extensions mid-session fails.
        importlib.import_module("tenacity")
        importlib.import_module("chromadb")
        # CRITICAL: After chromadb re-import, check if chromadb.api is wrongly bound to chromadb
        _ca = sys.modules.get("chromadb.api")
        _c = sys.modules.get("chromadb")
        if _ca is not None and _ca is _c:
            # chromadb.api is the same object as chromadb — this is the circular bug.
            # Delete and re-import so chromadb.api gets its own module identity.
            for _k in list(sys.modules.keys()):
                if _k == "chromadb.api" or _k.startswith("chromadb.api."):
                    del sys.modules[_k]
            importlib.import_module("chromadb.api")
            importlib.import_module("chromadb.api.segment")
        importlib.import_module("core.retrieval.reranker")

        # CRITICAL: Restore REAL sentence_transformers / torch / transformers BEFORE
        # re-importing core/retrieval modules. test_gap_a_retriever._stub() replaces
        # sys.modules["sentence_transformers"] (and torch, transformers) with MagicMock
        # stubs. We restore the real ones so the re-imported modules pick up the
        # real implementations at class-definition time.
        if _real_sentence_transformers is not None:
            sys.modules["sentence_transformers"] = _real_sentence_transformers
        if _torch_mod is not None:
            sys.modules["torch"] = _torch_mod
        if _transformers_mod is not None:
            sys.modules["transformers"] = _transformers_mod

        # CRITICAL: Re-import the ENTIRE core/retrieval module chain AFTER restoring
        # sentence_transformers, to ensure ALL cached class references are refreshed.
        # core/retrieval/retriever was imported BEFORE conftest's cleanup (when
        # sentence_transformers was MagicMock), so it holds a cached reference to the
        # OLD EmbeddingManager class. Simply re-importing vector_store and embeddings
        # does NOT update retriever's cached reference. We must also delete and re-import
        # core/retrieval/retriever.
        # The import order (embeddings → vector_store → retriever) ensures each module
        # picks up the real SentenceTransformer from the already-restored sys.modules.
        _keys_to_reimport = [
            "core.retrieval.embeddings",
            "core.retrieval.vector_store",
            "core.retrieval.retriever",
        ]
        for _k in _keys_to_reimport:
            if _k in sys.modules:
                del sys.modules[_k]
        for _k in _keys_to_reimport:
            try:
                importlib.import_module(_k)
            except ImportError:
                pass  # submodule may not exist as a standalone import

        # CRITICAL: Fix cached chromadb references in all retrieval modules.
        # test_gap_a_retriever patches sys.modules["chromadb"].PersistentClient = MagicMock().
        # conftest replaces sys.modules["chromadb"] with the real module, but the
        # re-imported vector_store module still holds a cached reference to the
        # OLD chromadb module. We fix this by patching the module attribute directly.
        real_chromadb = sys.modules.get("chromadb")  # the REAL module (just re-imported)
        vs_mod = sys.modules.get("core.retrieval.vector_store")
        if vs_mod is not None:
            setattr(vs_mod, "chromadb", real_chromadb)
        # Also fix sys.modules["chromadb"] in case test_gap_a_retriever's module-level
        # code OVERWROTE it with the stub after our initial re-import.
        # IMPORTANT: Only touch sys.modules["chromadb"] (root). Do NOT replace
        # sys.modules["chromadb.api"] or sys.modules["chromadb.api.segment"] —
        # those are correctly set by the fix above and replacing
        # them with the root module re-creates the chromadb.api-is-chromadb bug.
        for _key in list(sys.modules.keys()):
            if _key == "chromadb":
                _mod = sys.modules.get(_key)
                _pc = getattr(_mod, "PersistentClient", None) if _mod else None
                if _pc is None or "MagicMock" in type(_pc).__name__:
                    sys.modules[_key] = real_chromadb

    # ------------------------------------------------------------------
    # Step 2: Regenerate synthetic corpus
    # ------------------------------------------------------------------
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")
    os.environ.setdefault("RERANKER_LOCAL_FILES_ONLY", "1")

    import uuid
    import yaml

    queries_yaml = PROJECT_ROOT / "tests/retrieval_quality_baseline" / "queries.yaml"
    with open(queries_yaml, encoding="utf-8") as fh:
        yaml.safe_load(fh)

    # Full 41-topic synthetic corpus matching scripts/generate_synthetic_corpus.py
    SYNTHETIC_TOPICS = [
        {"page": 1, "keywords": ["part 25", "amendment", "airworthiness", "certification"],
         "text": "FAA Part 25 — Amendments through Amdt. 25-146, 2022. This subchapter establishes airworthiness standards for transport category airplanes with a maximum takeoff weight exceeding 12,500 pounds. Certification requirements cover structures, systems, powerplant, flight envelope, and environmental systems."},
        {"page": 25, "keywords": ["stall warning", "stall demonstration", "stall speed", "mcdu"],
         "text": "§25.203 Stall Demonstration. The applicant must demonstrate that the airplane can be safely controlled at speeds below V_S. Stall warning must be provided sufficiently in advance of the stall to allow the pilot to prevent the stall from occurring. The stall warning system must activate at a speed not less than the speed resulting from 1.25g pull-out at V_S."},
        {"page": 71, "keywords": ["fatigue", "widespread fatigue damage", "wfd", "limit of validity"],
         "text": "§25.571 Damage Tolerance and Fatigue Evaluation of Structure. The applicant must evaluate the airplane structure for the possibility of widespread fatigue damage (WFD). WFD is the distributive damage that may occur in a principal structural element at a number of locations simultaneously. The limit of validity (LOV) must be established."},
        {"page": 72, "keywords": ["fatigue", "fatigue test", "wing", "control surfaces", "limit of validity"],
         "text": "§25.572 Fatigue Test of Wing and Control Surfaces. A fatigue test must be performed on each wing and each control surface including the main rotor. The test must be conducted until the structure fails or until a total of 100,000 flights have been accumulated."},
        {"page": 78, "keywords": ["bird strike", "bird ingestion", "engine bird ingestion", "rotor blade"],
         "text": "§25.775 Bird Strike Certification. The airplane must be designed to ensure that each windshield, window, and windshield wiper can withstand the impact of a four-pound bird at cruise speed without penetration. Engine cowls and essential airframe surfaces must be evaluated for bird impact."},
        {"page": 86, "keywords": ["parking brake", "brake system", "braking system", "parking"],
         "text": "§25.735 Brakes and Braking Systems. The airplane must have a braking system that enables the pilot to maintain braking action under all conditions. The parking brake must be capable of holding the airplane stationary on a 1.2% uphill gradient with all engines at takeoff power."},
        {"page": 95, "keywords": ["emergency exits", "exit certification", "emergency evacuation", "exit lighting"],
         "text": "§25.809 Emergency Exit Arrangement. Each emergency exit must be accessible to all occupants and operable from inside and outside the airplane. The exit must be marked with readable instructions. Emergency exit lighting must be installed to illuminate the exit and the escape route."},
        {"page": 105, "keywords": ["lower deck", "lower deck evacuation", "cargo compartment", "evacuation"],
         "text": "§25.812 Emergency Lighting — Lower Deck Areas. Lower deck emergency lighting must be provided in cargo compartments and areas accessible to crew during emergency conditions. The illumination level must enable crew to identify trip hazards and locate emergency equipment."},
        {"page": 115, "keywords": ["fuel tank vent", "fuel tank", "vent system", "flammability"],
         "text": "§25.975 Fuel Tank Pressure and Vent System. Each fuel tank must be vented to the outside and be capable of preventing structural damage from pressure differentials. The vent system must prevent fuel spillage during flight maneuvers and ground operations."},
        {"page": 152, "keywords": ["lightning", "lightning strike", "lightning protection", "bonding"],
         "text": "§25.1316 Lightning Protection. The airplane must be protected against the effects of lightning strikes. All critical systems and structure must be designed to withstand lightning direct effects and indirect effects. Bonding and grounding provisions must prevent dangerous spark ignition of flammable vapors."},
        {"page": 169, "keywords": ["hydraulic", "hydraulic system", "hydraulic power", "landing gear"],
         "text": "§25.1435 Hydraulic Systems. Each hydraulic system must be designed to supply the hydraulic loads required for safe flight and landing. At least one independent hydraulic system must be provided for brakes and landing gear."},
        {"page": 176, "keywords": ["vfe", "flap", "v_s", "v_fe", "flap limit speeds"],
         "text": "§25.101 Flight Envelope — General. The airplane must demonstrate safe operation throughout the flight envelope. VFE is the maximum speed for flap extension. Exceeding VFE may result in flap structural damage. The flight manual must contain the correct VFE for each flap setting."},
        {"page": 183, "keywords": ["ewis", "electrical wiring", "wiring interconnection system", "flammability"],
         "text": "§25.1731 Electrical Wiring Interconnection System (EWIS). The EWIS must be designed to ensure safe operation throughout the service life of the airplane. EWIS includes wires, cables, connectors, bus bars, switchgear, and terminal boards. Flammability and toxicity requirements apply to all wire insulation materials."},
        {"page": 190, "keywords": ["ice protection", "icing", "anti-ice", "deice", "flight in icing"],
         "text": "§25.1419 Flight in Icing Conditions. The airplane must be capable of safe operation in continuous maximum icing conditions. All critical surfaces must have ice protection systems. Engine air inlet anti-icing must prevent ice buildup that could cause power loss or structural damage."},
        {"page": 200, "keywords": ["fire protection", "firewall", "fire resistance", "fire extinguishing"],
         "text": "§25.1181 Cargo Compartment Fire Protection. Each cargo compartment must have a fire extinguishing or suppression system capable of controlling a fire. Firewalls must be constructed to withstand the effects of fire and prevent fire penetration."},
        {"page": 210, "keywords": ["powerplant", "engine fire", "firewall", "fire detection", "fire extinguishing"],
         "text": "§25.1191 Powerplant Fire Protection — Firewall. Each engine must be separated from the airplane structure by a firewall capable of withstanding the effects of fire. Fire detection and extinguishing systems must be provided for each engine."},
        {"page": 220, "keywords": ["heat protection", "cabin temperature", "environmental control", "ecs"],
         "text": "§25.831 Ventilation and Heating. The environmental control system must provide adequate ventilation and temperature control for all occupied compartments. Cabin air pressure must be maintained at safe levels during flight."},
        {"page": 230, "keywords": ["apu", "auxiliary power unit", "fire protection", "fire detection"],
         "text": "§25.1203 Auxiliary Power Unit Fire Protection. The APU compartment must be isolated from the airplane by a firewall. Fire detection and extinguishing systems must be provided for the APU bay."},
        {"page": 240, "keywords": ["blade containment", "turbine", "compressor", "engine containment"],
         "text": "§25.905 Engine Rotor Blade and Turbine Blade Containment. Each engine must be designed to contain rotor blade and turbine blade failures without damage to the airplane."},
        {"page": 250, "keywords": ["electrical system", "generator", "battery", "power supply"],
         "text": "§25.1351 Electrical Power Supply and Distribution. The electrical power system must be capable of supplying all required loads under all operating conditions."},
        {"page": 15, "keywords": ["takeoff", "landing", "climb", "gradient"],
         "text": "§25.101 Takeoff speeds and takeoff climb requirements establish minimum performance standards for safe operations at maximum certificated takeoff weight."},
        {"page": 35, "keywords": ["stall speed", "v_s", "cl", "lift coefficient"],
         "text": "§25.103 Stall speed characteristics must be determined to establish the flight envelope boundaries for all configurations."},
        {"page": 45, "keywords": ["landing distance", "brake energy", "landing field length"],
         "text": "§25.125 Landing distance must be determined for all approved landing configurations at maximum certificated landing weight."},
        {"page": 55, "keywords": ["climb", "v2", "takeoff climb", "enroute climb"],
         "text": "§25.111 All-engine climb and one-engine-inoperative climb requirements ensure the airplane can safely clear obstacles after takeoff."},
        {"page": 60, "keywords": ["controllability", "maneuverability", "trim", "longitudinal"],
         "text": "§25.143 The airplane must be controllable and maneuverable during all phases of flight without requiring exceptional piloting skill."},
        {"page": 65, "keywords": ["longitudinal stability", "stick force", "speed stability", "pull force"],
         "text": "§25.175 Longitudinal stability requirements ensure the airplane returns to trimmed conditions after small speed perturbations."},
        {"page": 125, "keywords": ["landing gear", "tire clearance", "steering", "gear retraction"],
         "text": "§25.723 Landing gear geometry and tire clearance must be demonstrated for all approved operations on paved and unprepared surfaces."},
        {"page": 130, "keywords": ["brake performance", "brake energy", "fade", "braking coefficient"],
         "text": "§25.735 Brake performance requirements establish maximum brake energy absorption capacity for the most critical landing configuration."},
        {"page": 140, "keywords": ["seat", "safety belt", "restraint", "occupant protection"],
         "text": "§25.785 Seats and safety belts must be designed to protect occupants during all anticipated crash loads and deceleration conditions."},
        {"page": 145, "keywords": ["flotation", "ditching", "emergency landing", "water landing"],
         "text": "§25.801 Ditching certification requires demonstration that the airplane can safely ditch and that occupants can evacuate onto flotation devices."},
        {"page": 155, "keywords": ["lightning direct effect", "lightning indirect effect", "puncture", "arcing"],
         "text": "§25.1316 Lightning direct effects include structural damage, puncture, and arcing that may cause fuel ignition or loss of essential functions."},
        {"page": 160, "keywords": ["hirf", "high intensity radiated field", "emc", "electromagnetic"],
         "text": "§25.1318 High Intensity Radiated Field (HIRF) certification requires that electronic systems withstand HIRF environments without degradation."},
        {"page": 165, "keywords": ["vibration", "flutter", "buffeting", "aerelasticity"],
         "text": "§25.251 Vibration and flutter requirements ensure the airplane is free from aeroelastic instabilities throughout the flight envelope."},
        {"page": 172, "keywords": ["mechanical systems", "piping", "flexible hoses", "installation"],
         "text": "§25.1185 Flammable fluid piping and ducts must be designed and installed to prevent leakage and minimize fire hazards."},
        {"page": 178, "keywords": ["oxygen", "oxygen system", "crew oxygen", "passenger oxygen"],
         "text": "§25.1440 Oxygen equipment must be installed to provide supplemental oxygen for all occupants during emergency descent at high altitude."},
        {"page": 185, "keywords": ["pneumatic", "bleed air", "air conditioning", "pressurization"],
         "text": "§25.1438 Pneumatic systems must supply air for cabin pressurization, air conditioning, and engine starting under all operating conditions."},
        {"page": 195, "keywords": ["fire detection", "overheat detection", "sensor", "fire warning"],
         "text": "§25.1203 Fire detection systems must provide unambiguous and timely warning to the flight crew of any fire in the engine or APU compartment."},
        {"page": 205, "keywords": ["cargo classification", "class a cargo", "class b cargo", "hazardous materials"],
         "text": "§25.855 Cargo compartment classification determines the applicable fire protection requirements based on the types of cargo permitted."},
        {"page": 215, "keywords": ["instruments", "flight instruments", "indicator", "display"],
         "text": "§25.1301 Airplane instruments must provide the flight crew with information necessary for safe operation under all anticipated conditions."},
        {"page": 225, "keywords": ["avionics", "flight management system", "navigation", "communication"],
         "text": "§25.1302 Avionics systems must perform their intended functions reliably and must not interfere with other aircraft systems."},
        {"page": 235, "keywords": ["autopilot", "autothrottle", "flight director", "mode confusion"],
         "text": "§25.1329 Flight guidance systems must not cause mode confusion or misleading flight crew interface behavior."},
        # CCAR-25 synthetic topics
        {"page": 300, "keywords": ["ccar-25", "china", "civil aviation", "caac"],
         "text": "CCAR-25是中国民用航空规章第25部，适用于最大起飞重量超过5,700公斤的运输类飞机。CCAR-25的要求与FAA Part 25基本一致，在某些细节上根据中国民航的具体情况进行了调整。"},
        {"page": 310, "keywords": ["ccar-25", "china civil aviation", "airworthiness", "certification"],
         "text": "CCAR-25适航审定要求申请人证明飞机符合所有适用的适航标准。审定过程包括设计评审、试验验证、制造质量控制等环节。"},
    ]


    # Generate embeddings using the REAL EmbeddingManager (sys.modules already restored)
    from core.retrieval.embeddings import EmbeddingManager
    from core.retrieval.vector_store import VectorStoreAdapter

    texts = [t["text"] for t in SYNTHETIC_TOPICS]
    manager = EmbeddingManager()
    emb_array = manager.encode(texts)
    embeddings = emb_array.tolist()

    # Build ChromaDB entries
    ids = [str(uuid.uuid4()) for _ in SYNTHETIC_TOPICS]
    chunks = [t["text"] for t in SYNTHETIC_TOPICS]
    metadatas = [{
        "source_id": f"faa_part25_synthetic_{t['page']}",
        "source": "FAA_Part25.pdf",
        "page": t["page"],
        "keywords": ",".join(t["keywords"]),
    } for t in SYNTHETIC_TOPICS]

    # Clear and repopulate ChromaDB
    store = VectorStoreAdapter()
    try:
        store.client.delete_collection(store.collection_name)
    except Exception:
        pass
    store = VectorStoreAdapter()
    store.collection.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)

