# SCH-01: Freeze contracts and configuration

**Status:** Complete (2026-10-31). **Depends on:** None. **Estimate:** 0.5–1 day.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Implementation branch

Before creating and checking out the new branch, verify that the current branch
is `master` and the working tree is clean: no staged, unstaged, or untracked
changes. The completed prerequisites must already be merged into `master`.
If either check fails, stop branch creation and resolve it without discarding
changes or automatically committing or stashing them.

Once these checks pass, create and switch from `master` to a new branch named
`SCH-01_Freeze_contracts_and_configuration`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

Give backend, persistence, runtime, and UI agents one executable contract so their
implementations can proceed independently without guessing at interfaces.

## Work and file ownership

- Create `app/scheduler/__init__.py`, `contracts.py`, `constants.py`,
  `configuration.py`, and `errors.py`; no worker starts on import.
- Create `docs/roadmap_scheduler/contracts.md` and `contract_examples.json`
  with typed schedule/run/health models, all API request/response examples,
  revision and idempotency behavior, error codes, and fake-handler fixtures.
- Define `BaseTaskHandler`, `BaseScheduleRepository`, `BaseClock`, and executor
  contracts. Define atomic repository operations for CRUD, claim, completion,
  recovery, manual requests, and retention before implementations split.
- Freeze lifecycle, trigger calculation, deletion race, and payload-snapshot
  semantics from the roadmap. Define strict validation and UTC serialization.
- Specify shared database/lock configuration and worker-only concurrency,
  polling, freshness, retention, and log settings. Proposed variables:
  `CV_BUILDER_DATABASE_PATH`, `CV_BUILDER_LOCK_DIR`, `CV_BUILDER_SCHEDULER_LOG_DIR`,
  `CV_BUILDER_SCHEDULER_MAX_WORKERS`, `CV_BUILDER_SCHEDULER_POLL_SECONDS`,
  `CV_BUILDER_SCHEDULER_RETENTION_DAYS`. Resolve relative paths against the project
  root, not the process working directory; reject invalid settings at startup.
- Own `requirements.txt` dependency changes: verify APScheduler 3.11.3 with the
  application environment and pin a tested Windows-compatible OS-lock library.
  Do not change the Jira automation requirements. Record supported Python and
  library versions, checking the matching official documentation.

## Acceptance and validation

Every route has populated, empty, conflict, validation-error, and offline-worker
examples where applicable. Handler payloads cannot name arbitrary callables.
Tests reject naive dates, booleans as integers, unknown task types/fields, and
invalid limits. Configuration resolves identical database/lock identities in web
and worker processes. Importing the package performs no database/network work.

Create and run `tests/test_scheduler_contracts.py` and
`tests/test_scheduler_configuration.py`; run dependency compatibility checks.
Validate the JSON fixture document and compare its schemas with UI/API needs.

**Handoff:** frozen interfaces, example fixtures, exact dependency pins, config
defaults, and any deviations from proposed roadmap defaults. SCH-02, SCH-03,
and SCH-07 can start together after this completes.

## Implementation handoff — 2026-10-31

Change reference: uncommitted SCH-01 changes on `Introduce_scheduler`, based on
`b6f855d22bfb5ae071e482e20f95909b196ac0d7`. No prerequisite tickets exist. Before
editing, the existing fetch/repository/preference/location checks passed: 35 tests
and 27 subtests. Initial `pip check` also passed. Git's parent-directory access
needed a read-only permission override; status then confirmed ticket-local changes.

Frozen interfaces and semantics: [contracts.md](../contracts.md).
Reusable fixtures: [contract_examples.json](../contract_examples.json), with
10 routes, 58 HTTP exchanges, all nine run states, and three fake-handler outcomes.
Use its fixed 2030 clock context for request validation. JSON examples were parsed
and every declared request/response model was validated by the acceptance tests.

Changed paths:

- `app/scheduler/__init__.py`, `contracts.py`, `constants.py`, `configuration.py`,
  `errors.py`.
- `requirements.txt`: APScheduler 3.11.3 and portalocker 4.4.2 pins.
- `tests/test_scheduler_contracts.py`, `tests/test_scheduler_configuration.py`.
- `docs/roadmap_scheduler/contracts.md`, `contract_examples.json`, this ticket,
  and the roadmap's status/completion notes.

Checks actually run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_job_search.py tests/test_job_search_repository.py tests/test_job_search_preferences.py tests/test_job_search_locations.py -q
.\.venv\Scripts\python.exe -m pip install APScheduler==3.11.3 portalocker==4.4.2
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip install --dry-run -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_contracts.py tests/test_scheduler_configuration.py tests/test_job_search.py tests/test_job_search_repository.py tests/test_job_search_preferences.py tests/test_job_search_locations.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_contracts.py tests/test_scheduler_configuration.py -q
```

Outcomes: dependency install/resolution succeeded and `pip check` found no broken
requirements. Combined regression run: **157 passed, 27 subtests passed**.
Final focused rerun after contract/fixture review: **122 passed**. The existing
FastAPI tests emitted 35 Python 3.14 asyncio deprecation warnings; no failures.
An AST audit found docstrings on every new class/function. Git whitespace checking
and final file-scope review are included in the completion report.

The focused suite verifies strict values/UTC, future/unchanged trigger handling,
unknown payloads/fields, fixture coverage and schemas, detached fake outcomes,
settings bounds/path collisions, separate-process path identities, import safety,
APScheduler options without starting it, and Windows OS-lock exclusion/release
after normal exit, exception and abrupt process exit. Child processes received
explicit temporary database, lock and log paths before imports; no application
database was opened by the scheduler tests. Existing regressions used their
temporary databases and fake scrapers. No production worker, startup registration,
real job-board access, or Jira automation was used.

Tested platform: Windows x64 / Python 3.14.7 only. Full application/UI/release
verification belongs to later tickets and was not run here. This ticket freezes
interfaces, not repository/runtime/API implementations. No migration version was
allocated, no existing shared business interfaces were changed, and no default
roadmap values were changed. SCH-03 must wire shared configuration and transactional
preference reference checks; SCH-02/SCH-06 must reuse existing location validation;
SCH-04 must honor the final start gate and the executor's `TaskResult | None`
future result. See contracts.md for every owner-specific integration obligation.

All SCH-01 acceptance criteria passed. SCH-02, SCH-03 and SCH-07 are ready to start.
