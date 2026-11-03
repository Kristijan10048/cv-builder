# Scheduler implementation verification — 2026-11-03

Implemented SCH-01 amendment through SCH-12 together on the existing
`Implement_scheduler` branch, following the user's request for one implementation
pass. No ticket branches, commits, merges, or startup registrations were created.
The earlier per-ticket branching instructions remain historical planning guidance.

## Delivered

- Migration **5**, `task_scheduler`: mapped `task_schedules`, `task_runs`,
  `scheduler_workers`, and `job_board_state`. JSON snapshots plus indexed relational
  lifecycle fields; unique timed occurrences, manual keys, and active executions.
- `python -m app.scheduler`: independent APScheduler dispatcher, bounded executor,
  database-specific singleton lock, UTC triggers, coalescing, overlap summaries,
  final start gate, recovery, fenced heartbeats, retention, and drain-on-shutdown.
- Shared board coordinator for manual and scheduled fetching; nonblocking OS locks,
  typed busy/cooldown outcomes, persistent Glassdoor 429 deadlines, existing upserts.
- All ten frozen API routes, safe structured errors, revision checks, durable
  run-now dedupe, tombstone history, and transactional saved-search deletion guard.
- Shared UI transport/date/lifecycle utilities and Scheduled Tasks screen with
  create/edit, pause/resume, run now, history pagination, worker health, retry keys,
  stale-response suppression, and visibility-scoped polling.
- Windows foreground launcher and [operations guide](../scheduler_operations.md).

Recovery, health, and retention persistence live in `repository.py`, with lifecycle
orchestration in `runtime.py`/`dispatcher.py`; separate wrapper-only modules were
unnecessary. Common query predicates live in `queries.py`; all other data queries
also use mapped SQLAlchemy expressions. Existing migrations 1–4 are unchanged.
Tests are grouped by system behavior rather than one file per roadmap ticket.

## Environment and final commands

Windows x64, CPython **3.15.2**, Node **24.22.1**, PowerShell **7.6.5**.
Application pins include APScheduler **3.11.3** and portalocker **4.4.2**.
The existing virtual environment lacked pytest; installed its pinned **9.2.0**
and test-runner dependencies. No Jira automation dependencies were installed.

Commands actually run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
node --test tests/theme.test.cjs tests/extension.test.cjs tests/ui_core.test.cjs tests/scheduled_tasks.test.cjs
node --check static/app.js
node --check static/ui_core.js
node --check static/scheduled_tasks.js
.\.venv\Scripts\python.exe -m pip check
.\scripts\Start-Scheduler.ps1 -ValidateOnly
git diff --check
```

Final results: **378 Python tests passed, 59 subtests passed; 31 Node tests passed**.
One existing Starlette deprecation warning recommends `httpx2` for TestClient.
Dependency, Python compilation, JavaScript syntax, launcher validation, and
whitespace checks passed. The final date-input normalization change was followed
by the complete Node suite and syntax checks. The complete Python suite passed
again after the final scraper-warning and unsupported-handler fixes (48.53 seconds).

Focused suites also ran during development: existing app/search/Glassdoor tests,
`test_scheduler_system.py`, `test_scheduler_migrations.py`, and
`tests/scheduler_integration/`. All final focused runs passed.

## Acceptance evidence

| Area | Evidence |
| --- | --- |
| Worker independent of FastAPI | A subprocess executes the real fetch handler with synthetic scraper data, saves postings, exits gracefully; a subsequently started web process reads them via real HTTP. |
| Restart and singleton ownership | Second worker rejected; clean restart retains completed history; forced process loss after posting commit recovers as interrupted without replay. |
| Atomic claims and edits | Independent connections race revision edits and same manual keys; two child processes race a timed claim; database partial unique index rejects a second active run. |
| Pause/delete races | Final start gate cancels claimed old revisions; already-running work can finish; tombstone history survives saved-search deletion. Create-versus-preference-delete race has no broken committed references. |
| Timing and capacity | Frozen-clock cases cover anchored intervals, coalescing, inclusive lateness, overlap precedence, missed once disablement, capacity-full deferral, manual expiry, and new-trigger survival during old once completion. |
| Dispatch failures | Submission rejection releases capacity; failed cancellation writes reconcile next pass. Corrupt persisted task definitions fail closed and stop heartbeat progress; no arbitrary task is imported or executed. |
| Job fetching | Real adapter/filter/upsert pipeline with fake boards covers successful, empty, partial and all-failed outcomes, captured criteria, duplicate upserts, removed preference failure, and safe errors. |
| Shared boards | Separate process holds a board lock; another cannot acquire it; forced holder exit releases it. Persisted cooldown blocks worker fetches across independent worker restarts. Rate-limit capture persists even when a scraper raises. |
| Migration and rollback | Concurrent child startup, fresh schema, v4 copy upgrade, preserved applications/preferences/postings/settings, repeated startup, rollback of failed DDL, old runner rejecting v5, and matching pre-upgrade backup reopened by v4 runner. |
| API and UI contract | Every management route exercised against executable schemas; strict bodies/queries, offline receipt, retained history, revision conflicts, safe errors. UI tests consume frozen fixtures. |
| Operations | PowerShell 7 launcher validated with paths containing spaces and invalid environment; invalid startup returns nonzero. Worker logs are separate and omit service payload logs. |

The process harness requires a marked disposable root and explicit child database,
locks and both log paths before importing application modules. It refuses missing
isolation, bounds readiness/exit waits, creates hidden Windows children, and stops
only processes it owns. Tests use no real job boards, LM Studio, or Jira services.

## Browser verification

Used the in-app browser against a temporary localhost web server and worker with
the synthetic scraper from `tests/scheduler_integration/worker.py`. The database
and logs were under `.pytest_cache/scheduler-preview`, separate from user data.

Verified in the actual browser:

- Empty schedules and offline worker messaging; no-preference guidance leads to
  saved-search creation; new-schedule control enables when a search exists.
- Create an interval schedule; pause; request manual execution while paused;
  inspect queued history; start the fake worker; observe success and one saved job.
- Edit the schedule; recurrence and paused state remain intact; run-now receipt
  refreshes from queued to succeeded, with no stale offline message.
- Scheduled results appear in Available Jobs. Manual fixture fetch updates the
  same posting without duplication; stored-result pagination controls still work.
- Navigate between Scheduled Tasks, Preferences, Available Jobs and Settings;
  collapse/expand the sidebar; inspect both light and dark themes.
- Inspect desktop layout and a 390×844 mobile viewport in both themes; no horizontal
  overflow. Form becomes one column; action buttons wrap. Tab from Name focuses
  Saved search. Restore the temporary viewport override afterward.
- No browser console errors at the end of the verification flow.

Local screenshots were captured as `.pytest_cache/scheduler-preview/dark-wide.png`,
`light-wide.png`, `light-mobile-form.png`, and `dark-mobile.png`. They are ignored
local review artifacts; the checklist above is the versioned visual evidence.

## Issues found and resolved

- Old Glassdoor expiry tests advanced a process-local monotonic clock. They now
  advance the shared UTC clock past the persisted cooldown deadline.
- An accepted queued/offline receipt remained visible after completion. The page
  now updates that receipt during polling, with a regression test.
- Native datetime inputs omit zero seconds. Form serialization now normalizes the
  same way, preserving unchanged past anchors during name/payload edits.
- Review found overlap-versus-lateness precedence needed alignment with the frozen
  contract: active overlap wins. Tests cover both simultaneous conditions.
- A transient DB error while recording executor rejection could retain a queued
  claim. Dispatcher reconciliation now retries that terminal write without rerun.
- Unexpected scraper `ValueError` messages could reach result warnings. Only typed
  board-validation messages are now shown; other scraper errors use a safe generic
  warning. Disabled registry entries record a terminal `unsupported_task` failure.
- Sandbox restrictions prevented pytest temporary directories and localhost preview
  access; the corresponding isolated checks ran with approved execution access.
- Windows PowerShell 5 rejected unsigned scripts under its existing execution
  policy. PowerShell 7 validation passed. The guide provides direct Python startup
  for environments where scripts are blocked; no policy was changed.

## Operational limits and checks not performed

No production database migration, production scraper run, persistent OS task
installation, multi-host/network-share deployment, or pre-login Windows service
test was performed. These are intentionally outside automated acceptance.
No live-board smoke test is required for this release.

Threads cannot forcibly cancel a hung scraper. Forced process-tree termination
may leave an interrupted execution whose jobs were already saved; recovery does
not replay uncertain work. Historical request keys expire when retention deletes
their terminal runs. Malformed stored definitions fail closed and require storage
repair or restoration; they are never dynamically executed. See the operations
guide for supervision, backup and matching-code/database rollback.
