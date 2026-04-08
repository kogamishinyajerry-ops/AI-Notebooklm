# Stack

## Runtime

- Python 3.11+
- Local-first CLI application
- No database server
- No web framework

## Primary Libraries

- `pydantic` v2 for domain models and validation
- `ruamel.yaml` for YAML parsing/writing
- `typer` for CLI commands
- `rich` for CLI output formatting
- `jsonschema` for schema support

## Testing

- `pytest`
- `pytest-cov` available in dev extras

## Tooling Facts

- Package entrypoint: `aplh`
- Repo currently has 50 code files under `aero_prop_logic_harness/`
- Repo currently has 17 pytest modules
- Repo currently has 178 YAML artifact/state files under `artifacts/`

## Operational Reality

- `validate-artifacts --dir artifacts` passes
- `check-trace --dir artifacts` passes
- `freeze-readiness --dir artifacts` fails only because docs/checklist are incomplete
- `pytest` is not fully green at the moment
