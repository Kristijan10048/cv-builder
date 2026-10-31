# SCH-07: Refactor shared UI utilities and page lifecycle

**Status:** Pending. **Depends on:** [SCH-01](SCH-01.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

New screens can reuse stable HTTP, date, and navigation helpers without expanding
the existing global script or introducing a frontend framework.

## Work and file ownership

- Create `static/ui_core.js` with a small explicit namespace for HTTP requests,
  error formatting, date formatting, escaping, and view enter/leave registration.
- Refactor `static/app.js` and script ordering in `templates/index.html` to use
  those utilities. Preserve compatibility wrappers for existing page scripts;
  remove wrappers only after all callers have migrated and been checked.
- Handle legacy SQLite timestamp strings and new offset-bearing ISO timestamps
  without double-appending timezone suffixes. Keep display in the user's locale.
- Represent structured API errors without displaying `[object Object]`; support
  abort signals and clean navigation teardown for future polling screens.
- Keep existing view IDs, sidebar behavior, page titles, Available Jobs toolbar,
  preferences, theme loading, toast behavior, and mobile layout intact.
- Do not build the scheduled-task screen yet or broadly split unrelated editors.
  Avoid CSS redesign and build-tool changes.

## Acceptance and validation

Create/run `tests/ui_core.test.cjs` using the existing Node test convention.
Cover JSON/object/array errors, 204 responses, non-JSON failures, aborted requests,
legacy and timezone-aware timestamps, escaping, and enter/leave ordering.

Run `tests/theme.test.cjs` and syntax-check changed scripts. In a disposable app,
manually verify navigation, sidebar collapse, both themes, Available Jobs fetch
and pagination, and preferences. Use synthetic records and a fake scraper.

**Handoff:** utility interface, lifecycle contract, compatibility wrappers, and
script order. SCH-08 takes ownership of index.html changes only after this task
finishes; SCH-02 and SCH-03 can run independently alongside this task.
