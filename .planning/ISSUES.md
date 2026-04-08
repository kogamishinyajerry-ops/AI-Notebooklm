# Deferred Issues

## Active Blockers

- **No git repository in workspace**
  Impact: stock GSD atomic task commits cannot run as designed.
  Current handling: keep `commit_docs: false`, treat execution as no-git mode until repo initialization is explicitly chosen.

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

- Add a no-git execution wrapper for GSD-style plan runs if git is intentionally never initialized.
- Teach cockpit sync to parse executed plan summaries and update Notion automatically after every plan completion.
- Add an Opus review result ingestion helper so manual review outputs can be converted into next-step phase updates.
