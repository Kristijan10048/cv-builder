# SCH-10: Verify the complete system and concurrent behavior

**Status:** Complete (2026-11-03). **Depends on:** [SCH-06](SCH-06.md), [SCH-08](SCH-08.md),
[SCH-09](SCH-09.md). **Estimate:** 1.5–2.5 days.

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
`SCH-10_Verify_the_complete_system_and_concurrent_behavior`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

Demonstrate independent operation and data safety with the real API, worker,
repository, and UI contracts, while using offline job-board fixtures.

## Work and file ownership

- Own `tests/scheduler_integration/` and its process harness; create a temporary
  database, lock directory, logs, and fake scraper configuration for every case.
  Pass settings to each child before imports. Refuse default production paths.
- Start disposable web/worker processes with bounded readiness deadlines and
  hidden windows where relevant. Clean up only processes/files the harness owns.
- Exercise create/edit/pause/resume/delete/run-now/history through real API calls,
  checking UI fixture schemas against actual responses.
- Fetch with FastAPI stopped, then start it and observe persisted jobs/history.
  Restart worker and web independently, reject a second worker, and test
  simultaneous migration startup.
- Race duplicate timed claims, repeated manual keys, edits, pause/delete, and
  saved-search deletion. Test downtime/coalescing, saturation, overlap, one-time
  expiry/completion, and interrupted recovery without rerun.
- Verify shared cooldown and board exclusion across manual and scheduled fetches,
  partial results, empty results, full failure, and safe recovery after contention.
- Add user-flow checks for real screen/API wiring and offline worker messaging;
  record keyboard, theme, navigation, and narrow-layout verification evidence.
- Report product defects to their owning tickets; do not silently change frozen
  contracts just to make integration checks pass.

## Acceptance and validation

Run the integration suite and existing Python/Node regressions after integrating
all prerequisites. Use deterministic clocks/fakes for timing boundaries and only
bounded real-time waits for process readiness. Tests must not access live boards,
the user's database, LM Studio, or Jira automation.

Write `docs/roadmap_scheduler/verification.md` with commands actually run,
environment, outcomes, failure reproduction, and any unresolved release blockers.

**Handoff:** reproducible integration harness and evidence for every roadmap
release criterion. SCH-11 documentation can proceed independently alongside this.
