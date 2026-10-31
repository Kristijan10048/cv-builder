# SCH-02: Extract the reusable job-fetch backend

**Status:** Implementation validated; final acceptance awaits the SCH-01 board-interface amendment (2026-10-31).
**Depends on:** [SCH-01](SCH-01.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Implementation branch

Before creating and checking out the new branch, verify that the current branch
is `master` and the working tree is clean: no staged, unstaged, or untracked
changes. The completed prerequisites must already be merged into `master`.
If either check fails, stop branch creation and resolve it without discarding
changes or automatically committing or stashing them.

Once these checks pass, create and switch from `master` to a new branch named
`SCH-02_Extract_the_reusable_job_fetch_backend`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

Manual fetching and future scheduled fetching call the same business service
without importing FastAPI routes or depending on HTTP exceptions.

## Work and file ownership

- Create `app/services/job_search_service.py`, `app/services/job_search_errors.py`,
  and an explicit dependency factory. Move orchestration/outcome behavior from
  `app/job_search.py`; leave a thin router translating domain errors to the
  existing HTTP responses. Preserve the replaceable scraper seam used by tests.
- Update `app/job_search_repository.py` to raise domain errors for missing or
  concurrently deleted preferences, preserving SQLAlchemy transactions and
  upsert/link behavior. Define a preference lookup/deletion service seam for
  SCH-06; do not implement schedule-specific deletion policy yet.
- Separate reusable search input/outcome types from transport concerns where
  needed, keeping existing request and response shapes unchanged.
- Allow injection of the board coordination interface agreed in SCH-01. Keep
  the current guard behavior until SCH-05 supplies cross-process coordination.
- Retain board parallelism, keyword/location filtering, result bounds, language
  extraction, warning semantics, and persistence after partial success.
- Dispose owned engines/resources deterministically. Do not refactor unrelated
  application, profile, document, or generation routes in this ticket.

## Acceptance and validation

The service can run with a fake scraper without importing `app.main`; service
and repository code contain no FastAPI exceptions. The existing API still returns
404 for a missing preference, 409 for deletion during fetching, and 502 when all
boards fail. Zero successful matches remain a success; partial results persist.

Run existing job-search, repository, Glassdoor, language, preference, and API
tests affected by the extraction. Add focused transport-independent service tests
in `tests/test_job_search_service.py`, including resource cleanup and injected
failures. Preserve all current test seams or migrate their callers explicitly.

**Handoff:** factory usage, error mapping, injected coordinator contract, and
evidence that manual fetching retains its existing behavior. SCH-05 and SCH-06
can consume this result independently once SCH-03 is also complete.

## Implementation handoff — 2026-10-31

Change reference: staged, uncommitted changes on `ticket_no`, based on
`72f65619ebd46979faef803625c04098e995dd14` (the SCH-01 merge). The checkout was
clean before work. No unrelated files, shared scheduler interfaces, migrations,
dependency pins, global fixtures, preference routes, or `app.main` were changed.

Prerequisite verification before editing: read AGENTS.md, the roadmap, execution
guide, SCH-01 handoff, contract documentation and executable contracts. The
SCH-01 contract/configuration tests and existing fetch/repository/preferences/
locations/Glassdoor/language tests passed together: **213 tests, 27 subtests**.
`pip check` found no broken requirements. The existing dependency compatibility,
isolated-process configuration and Windows lock checks were included.

Changed files:

- `app/job_search.py`: thin HTTP adapter; retains `scrape_jobs` monkeypatch seam,
  service/outcome import aliases, logging category, response shapes and errors.
- `app/job_search_adapter.py`: injectable coordinator and unchanged default
  process-local Glassdoor behavior, including its replaceable global guard.
- `app/job_search_repository.py`: domain failures, explicit engine disposal and
  preference deletion with a guard inside `BEGIN IMMEDIATE`.
- `app/services/__init__.py`, `job_search_service.py`, `job_search_errors.py`,
  `job_search_dependencies.py`: reusable fetching, preference service and factory.
- `tests/test_job_search_service.py`: 15 focused offline service/seam checks.
- This ticket and `scheduler_roadmap.md`: implementation status and handoff.

### Factory and execution-start snapshot

```python
from app.services.job_search_dependencies import JobSearchServiceFactory

with JobSearchServiceFactory(scraper=fake_scraper).create() as service:
    response = service.search(payload)
    # A scheduled handler instead calls fetch once, with its snapshot callback:
    # outcome = service.fetch(payload, on_preference=record_effective_preference)
```

`search(JobSearchInput)` returns the unchanged manual response.
`fetch(JobSearchInput, on_preference=None)` returns `JobSearchOutcome` after
persistence. It reads current criteria at execution start and passes a detached
copy to the callback before starting any board. Callback errors abort fetching;
callback mutations do not change the effective criteria used by the adapters.
SCH-05 converts the criteria into the existing `PreferenceSnapshot` contract
(excluding database timestamps) and calls `record_effective_preference` there.
This does not replace or mutate the scheduler's claim snapshot.

The factory lazily constructs dependencies and disposes its owned repository in
`finally`, including construction, lookup, snapshot, scraper and storage failures.
`create(repository=existing_repository)` borrows storage; its caller closes it.
Injected scraper/coordinator resources are also borrowed. Concurrent board work
drains before the factory closes storage. Reusable modules import no FastAPI or
routes; a fresh-interpreter test actively rejects those imports while performing
a fetch against a temporary migrated database. `JobSearchInput` remains in
`app.models`, which already has no transport dependency.

### Domain failures and preference seam

| Domain error | Manual HTTP mapping |
| --- | --- |
| `PreferenceNotFoundError` | 404, unchanged string detail |
| `PreferenceDeletedError` | 409, unchanged concurrent-deletion detail |
| `AllBoardsFailedError` | 502, unchanged message/warnings detail |

`AllBoardsFailedError` also carries copied per-board diagnostics for SCH-05.
Unknown board exceptions still produce the existing generic public warning;
partial results and zero-match successes preserve their existing behavior.
SCH-06 must apply its own frozen scheduler error envelope rather than reuse the
manual HTTP translation (missing create/replace preferences are 422 there).

`JobSearchPreferenceService.get_preference()` returns current detached criteria;
`validate_search()` applies existing offline country resolution and board rules
to every selected site without fetching. `delete_preference(preference_id, guard)`
calls `BasePreferenceDeletionGuard.validate_deletion(connection, preference_id)`
inside the same locked transaction that deletes the preference. SCH-06 must use
that connection for the live schedule-reference query and raise its domain
conflict there. Calling `referencing_schedule_ids()` separately is not sufficient.
No schedule-specific deletion policy is implemented or wired into routes here.

### Required shared-interface integration proposal

SCH-01's checked-in contract specifies coordination semantics, but it has **no
board coordinator interface**, despite this ticket requiring an agreed interface.
Reopen SCH-01 for that amendment; do not treat this local proposal as frozen or
unblock the affected SCH-05 integration until the contract owner resolves it.
No shared contract files have been edited by SCH-02.

Proposed starting seam, implemented locally in `app/job_search_adapter.py`:
`BaseJobBoardCoordinator.search(scraper, arguments) -> (result_frame, warning)`.
The arguments contain exactly one validated board; calls may run concurrently
for distinct boards. The coordinator owns exclusion/cooldown around the scrape,
returns accepted data plus an optional warning, and releases resources before
returning or raising. The adapter retains normalization, filters and partial
posting handling. The factory accepts the coordinator explicitly.

The default `LocalJobBoardCoordinator` deliberately retains current Glassdoor
locking/cooldown. SCH-01/SCH-05 must settle typed busy/cooldown diagnostics as part
of the amendment so SCH-05 can produce the frozen `BoardResult` statuses without
parsing warning text. The current tuple alone does not distinguish those states.
OS-backed nonblocking exclusion and persisted cooldown are SCH-05 work, not claims
made by this extraction. SCH-06's preference seam can be integrated independently
after SCH-03. SCH-09 must also route/sanitize service logging for worker use: this
ticket retains existing manual logging, including preference diagnostics.

### Checks actually run and outcomes

Commands used the project-local Windows Python 3.14.7 environment:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_contracts.py tests/test_scheduler_configuration.py tests/test_job_search.py tests/test_job_search_repository.py tests/test_job_search_preferences.py tests/test_job_search_locations.py tests/test_job_search_glassdoor.py tests/test_job_language_requirements.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_job_search.py tests/test_job_search_repository.py tests/test_job_search_preferences.py tests/test_job_search_locations.py tests/test_job_search_glassdoor.py tests/test_job_language_requirements.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_job_search_service.py -vv -o faulthandler_timeout=20
.\.venv\Scripts\python.exe -m pytest tests/test_job_search.py -vv -x -o faulthandler_timeout=20
.\.venv\Scripts\python.exe -m pytest tests/test_job_search_service.py -q --tb=short -o faulthandler_timeout=20
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_contracts.py tests/test_scheduler_configuration.py tests/test_job_search_service.py tests/test_job_search.py tests/test_job_search_repository.py tests/test_job_search_preferences.py tests/test_job_search_locations.py tests/test_job_search_glassdoor.py tests/test_job_language_requirements.py tests/test_app.py tests/test_request_logging.py -q --tb=short -o faulthandler_timeout=30
git diff --check
git diff --cached --check
```

Final combined result: **248 passed, 27 subtests passed**, with 35 existing
FastAPI/Python asyncio deprecation warnings. Focused service run: **15 passed**;
manual API rerun: **17 passed**. `pip check` passed before and after implementation.
AST parsing/docstring audit passed for every changed Python file. Git whitespace
checks and staged file-scope review passed.

Intermediate attempts: the first post-extraction regression invocation produced
no output and was interrupted; its cause was not established. The verbose API
rerun and final combined run completed successfully. The initial new-test run
failed because its fixture supplied a positive radius with no city, violating
the existing schema; the fixture was corrected to radius zero before both passing
runs. Neither attempt is counted as a successful check.

All executable extraction acceptance checks pass. Formal ticket completion remains
gated on the missing agreed board interface above. Full release/UI and future
cross-process coordination acceptance remain with their owning tickets. Tests
used temporary databases and offline/fake boards; child processes received
explicit temporary paths. No production worker, startup task registration, real
job-board access, Jira automation, or migration allocation occurred.
