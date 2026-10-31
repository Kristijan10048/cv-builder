# SCH-04: Implement the independent APScheduler runtime

**Status:** Pending. **Depends on:** [SCH-03](SCH-03.md).
**Estimate:** 1.5–2.5 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

An independently launched process dispatches durable tasks on time with bounded
concurrency and an extensible handler registry.

## Work and file ownership

- Create `app/scheduler/__main__.py`, `runtime.py`, `dispatcher.py`,
  `triggers.py`, `registry.py`, and `worker_lock.py`.
- Acquire the database-specific OS lock, initialize schema through SCH-03, and
  launch a `BlockingScheduler` with one five-second dispatcher. Keep the main
  process alive and release the lock only after execution resources stop.
- Use the memory job store only for the dispatcher. Read domain schedules and
  queued manual runs from the repository; do not introduce APScheduler's
  persistent job store or start a scheduler inside FastAPI.
- Implement interval anchors, one-time completion, UTC date handling, coalescing,
  lateness/missed records, overlap skipping, fair selection of due work, and
  capacity reservation before claims. Alternate manual/timed selection so one
  workload cannot starve the other.
- Submit only committed snapshots to a bounded executor. Recheck invalidated
  queued claims before invocation and record cancellation. Dispatch failure
  cannot silently lose a claim or leave a permanently active in-process run.
- Implement extensible registry dispatch using SCH-01 schemas; unknown type or
  payload version fails safely. A test handler proves extensibility.
- Provide lifecycle hooks for recovery, health, logging, and retention that
  SCH-09 will finish. This ticket alone is not release-ready.

## Acceptance and validation

Create/run `tests/test_scheduler_runtime.py` and `tests/test_scheduler_triggers.py`
with injected clocks and a fake executor. Cover anchor preservation, late ticks,
full capacity, repeated ticks, manual request expiry, pause/resume, revisions,
one-time disablement, nonoverlap, and dispatcher exceptions. No long real sleeps.

Use one bounded process-level smoke test to prove the process stays alive,
executes a fake task without FastAPI, rejects a second worker, and exits cleanly.

**Handoff:** runtime lifecycle, handler registration seam, shutdown behavior,
and fake-worker launcher for SCH-09 and later integration tests.
