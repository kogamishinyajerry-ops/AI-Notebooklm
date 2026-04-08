# Deferred Issues

## Active Blockers

- **Pytest is not fully green**
  Impact: automation cockpit must surface current repo risk before treating the repository as fully healthy.
  Current status: `311 passed / 7 failed` on 2026-04-09.
  Failure clusters:
  - `freeze-readiness` tests still expect an empty/weak graph failure, but repo now fails on docs incomplete instead.
  - Phase 4 tests detect `artifacts/.aplh/promotion_manifests/` in the formal baseline.
  - Phase 7 tests still expect a `50`-file controlled population inventory, but repo currently yields `51`.

- **Freeze-readiness still blocked by docs**
  Impact: final freeze signoff cannot begin.
  Current handling: Phase 13 onward is dedicated to checklist/docs completion and review.

## Deferred Enhancements

- Teach cockpit sync to parse executed plan summaries and update Notion automatically after every plan completion.
- Add an Opus review result ingestion helper so manual review outputs can be converted into next-step phase updates.
