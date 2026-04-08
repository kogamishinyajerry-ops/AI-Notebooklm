# Integrations

## Internal Runtime Integrations

- File-system scanning of `artifacts/`
- YAML loading through `ruamel.yaml`
- Pydantic model validation
- CLI orchestration via `typer`

## Governance / Process Integrations

- Notion control hub managed through `scripts/notion_control_hub.py`
- GSD workflow definitions live in `~/.codex/get-shit-done/`
- `.planning/` provides local GSD execution memory

## Human Review Integrations

- Opus 4.6 is an external human-triggered review step
- Later manual freeze authority remains outside Codex/Notion automation

## Non-Integrations

- No database service
- No hosted web app
- No production message bus
- No direct cloud dependency for core artifact operations
