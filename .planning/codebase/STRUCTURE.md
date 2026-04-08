# Structure

## Top-Level Layout

- `aero_prop_logic_harness/` — application code
- `artifacts/` — formal/demo artifact truth plus `.aplh` governance state
- `docs/` — accepted plans, reports, governance docs, and milestone board
- `schemas/` — artifact schema files
- `templates/` — YAML / document templates
- `tests/` — pytest coverage across phases and CLI behavior
- `scripts/` — repo automation helpers, including Notion/GSD cockpit tooling
- `.planning/` — GSD execution memory and codebase map

## Code Layout

- `models/` — domain objects and state artifacts
- `loaders/` — YAML loading and artifact parsing
- `services/` — readiness, promotion, scenario, replay, population, and freeze review services
- `validators/` — schema, trace, consistency, coverage, and mode validators

## Documentation Layout

- `README.md` — project entrypoint and current state
- `docs/MILESTONE_BOARD.md` — best human-readable status board
- `docs/POST_PHASE7_*` — current governance chain and accepted evidence
- `docs/PHASE*` — historical plans, implementation notes, and reviews

## Planning Layout

- `.planning/PROJECT.md` — living project definition
- `.planning/ROADMAP.md` — remaining GSD roadmap
- `.planning/STATE.md` — short-term execution memory
- `.planning/codebase/` — codebase map
- `.planning/phases/` — executable current/future phase context and plans
