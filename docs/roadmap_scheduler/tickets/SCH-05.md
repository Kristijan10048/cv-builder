# SCH-05: Integrate job fetching and shared board coordination

**Status:** Complete (2026-11-03). **Depends on:** [SCH-02](SCH-02.md), [SCH-03](SCH-03.md).
**Estimate:** 1–2 days.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

**Integrated handoff:** Delivered on the existing `Implement_scheduler` branch
in the single implementation pass requested by the user. See
[verification and release evidence](../verification.md) for changed areas,
grouped test locations, commands, results, migration 5, browser checks and
operating limits. This handoff supersedes historical pending gates and branch
instructions below; no automatic commits or merges were performed.

## Implementation branch

Before creating and checking out the new branch, verify that the current branch
is `master` and the working tree is clean: no staged, unstaged, or untracked
changes. The completed prerequisites must already be merged into `master`.
If either check fails, stop branch creation and resolve it without discarding
changes or automatically committing or stashing them.

Once these checks pass, create and switch from `master` to a new branch named
`SCH-05_Integrate_job_fetching_and_shared_board_coordination`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

The first handler fetches jobs with existing application behavior, and overlapping
manual/scheduled searches respect the same board exclusion and cooldown state.

## Work and file ownership

- Create `app/scheduler/handlers/__init__.py`, `handlers/fetch_jobs.py`, and
  `app/services/job_board_coordinator.py` using the earlier contracts.
- Resolve the current preference at execution start; capture effective criteria,
  selected boards, result limit, and payload version in the run snapshot. Reuse
  the shared service, adapter, filters, and result persistence.
- Map all-failed/missing-preference cases to failure; any board failures or
  partial-board warnings with successful boards to partial; successful empty
  results to success. Preserve per-board counts and sanitized warnings.
- Extend `app/job_search_glassdoor.py` and the SCH-02 factory to inject the same
  cross-process board coordinator for manual and scheduled fetching. An OS lock
  covers each board scrape and any rate-limit capture, and releases on crashes.
- Persist Glassdoor cooldown deadlines through SCH-03. A process restart must
  not reset a known cooldown. Use nonblocking lock acquisition; busy/cooling
  boards produce explicit warnings while other boards proceed.
- Do not hold database transactions during scraping. Do not add new boards,
  retry loops, arbitrary URLs, or a second job-storage implementation.
- Export the handler factory; SCH-09 owns final runtime registration, avoiding
  parallel edits to runtime files owned by SCH-04.

## Acceptance and validation

Create/run `tests/test_scheduler_fetch_handler.py` and
`tests/test_job_board_coordinator.py`; rerun existing Glassdoor/manual-fetch
regressions. Verify duplicate-posting upserts, preference edits/deletion races,
all-board failure, empty success, partial persistence, and cleanup after errors.

Use fake scrapers in two processes to prove board exclusion and persisted cooldown
across a worker restart. Confirm a busy board cannot indefinitely block others.

**Handoff:** handler factory, result/error mapping, shared coordinator integration,
and cross-process verification evidence. SCH-04 need not finish before this task.
