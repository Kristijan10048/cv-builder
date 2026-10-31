# SCH-09: Finish recovery, health, and operational reliability

**Status:** Pending. **Depends on:** [SCH-04](SCH-04.md), [SCH-05](SCH-05.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Outcome

The real job handler is wired into the independent runtime, and failures,
restarts, stale workers, logs, and retained history have predictable behavior.

## Work and file ownership

- Register the SCH-05 handler and shared board coordinator in the runtime.
  Validate all configuration before claiming business work.
- Create `app/scheduler/recovery.py`, `health.py`, `logging_setup.py`, and
  `retention.py`; update SCH-04 lifecycle hooks now that their owner is done.
- After singleton acquisition, mark abandoned queued/running work interrupted,
  preserve completed records/results, and never automatically replay uncertain
  work. Document the crash-after-persistence window in errors and tests.
- Write owner-scoped heartbeats from successful dispatcher progress, with a
  30-second freshness threshold. Stop freshness when dispatch is stuck/failing;
  distinguish running tasks from a failed dispatcher.
- Configure `scheduler.log` separately from `applykit.log`, INFO by default,
  including identifiers, duration, and safe outcomes. Prevent inherited service
  TRACE/payload logging from leaking job descriptions into worker logs.
- Run bounded retention batches for terminal records; preserve active records,
  required tombstones, and the documented manual-request dedupe window.
- Stop new claims on shutdown, drain work, close resources, and release ownership
  last. Define supervisor force-stop behavior for hung scraper threads without
  pretending a thread timeout cancels network work.

## Acceptance and validation

Create/run `tests/test_scheduler_recovery.py`, `test_scheduler_health.py`, and
`test_scheduler_logging.py`. Cover stale owner recovery, worker death before/after
job persistence, dispatch versus handler failure, malformed stored payload,
retention boundaries, stopped/stale health, and redacted separate logs.

Use bounded fake tasks to test graceful stop and a disposable process tree for
forced-stop recovery. Recheck worker ownership after a crash and verify manual
fetch still observes persisted cooldown. No automatic retries occur.

**Handoff:** integrated runtime, documented shutdown limits, recovery evidence,
health fields, and safe logging defaults for SCH-10 and SCH-11.
