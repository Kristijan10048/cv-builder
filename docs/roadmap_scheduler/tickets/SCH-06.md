# SCH-06: Add schedule management API

**Status:** Pending. **Depends on:** [SCH-02](SCH-02.md), [SCH-03](SCH-03.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

The web app manages durable schedule definitions and execution requests without
owning the worker or starting work during an HTTP request.

## Work and file ownership

- Create `app/scheduler/api.py` and `management_service.py` using SCH-01 models
  and SCH-03 repository operations. Implement every roadmap management/status
  endpoint and register the router in `app/main.py`.
- Implement revision conflicts, pagination, task/payload validation, enabled and
  deleted state, run-history access, manual idempotency, and offline-worker status.
  Return an existing request for a repeated idempotency key; reject reuse with
  incompatible input. An unrelated active run returns 409.
- Validate preferences on create/edit and preserve referential integrity across
  concurrent preference deletion. Integrate the live-schedule deletion guard
  into `app/job_search_preferences.py` through the SCH-02 service seam.
- Translate domain errors to stable HTTP errors without exposing internal
  tracebacks. Define 503 for temporary database unavailability.
- Keep schedule edits usable when no worker is running. Run-now returns a durable
  queued request and status, not a fabricated completion or direct scraper call.
- Do not edit UI files, runtime files, or migration definitions in this task.

## Acceptance and validation

Create/run `tests/test_scheduler_api.py`; rerun preference and application API
regressions. Test every route against contract examples, including invalid types,
stale revisions, repeated keys, absent/deleted schedules, retained history,
pagination, paused run-now, active-run deletion messaging, and storage failures.

Verify API startup never starts APScheduler and no management endpoint calls a
scraper. Test create-versus-preference-delete conflicts with independent database
connections. Assert offline health is distinct from an empty schedule list.

**Handoff:** live endpoint examples, error mapping, router wiring, and fixture
compatibility evidence. SCH-08 may already be developing against SCH-01 fixtures.
