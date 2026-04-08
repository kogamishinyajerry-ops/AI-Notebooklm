import json
from pathlib import Path

from aero_prop_logic_harness.models import (
    Requirement,
    Function,
    Interface,
    Abnormal,
    GlossaryEntry,
    TraceLink,
    # Phase 2A additions
    Mode,
    Transition,
    Guard,
)

SCHEMA_DIR = Path("schemas")

def dump_schema(model_cls, filename: str):
    schema = model_cls.model_json_schema()
    out_path = SCHEMA_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"Dumped {out_path}")

def validate_schemas():
    dump_schema(Requirement, "requirement.schema.json")
    dump_schema(Function, "function.schema.json")
    dump_schema(Interface, "interface.schema.json")
    dump_schema(Abnormal, "abnormal.schema.json")
    dump_schema(GlossaryEntry, "glossary.schema.json")
    dump_schema(TraceLink, "trace_link.schema.json")
    # Phase 2A additions
    dump_schema(Mode, "mode.schema.json")
    dump_schema(Transition, "transition.schema.json")
    dump_schema(Guard, "guard.schema.json")

if __name__ == "__main__":
    validate_schemas()
