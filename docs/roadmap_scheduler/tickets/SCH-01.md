# SCH-01: Freeze contracts and configuration

**Status:** Pending. **Depends on:** None. **Estimate:** 0.5–1 day.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

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
  `APPLYKIT_DATABASE_PATH`, `APPLYKIT_LOCK_DIR`, `APPLYKIT_SCHEDULER_LOG_DIR`,
  `APPLYKIT_SCHEDULER_MAX_WORKERS`, `APPLYKIT_SCHEDULER_POLL_SECONDS`,
  `APPLYKIT_SCHEDULER_RETENTION_DAYS`. Resolve relative paths against the project
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
