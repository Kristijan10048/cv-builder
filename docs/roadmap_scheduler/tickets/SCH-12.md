# SCH-12: Integrate and accept the release

**Status:** Complete (2026-11-03). **Depends on:** [SCH-10](SCH-10.md), [SCH-11](SCH-11.md).
**Estimate:** 0.5–1 day.

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
`SCH-12_Integrate_and_accept_the_release`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

Deliver one coherent scheduler release whose implementation, migrations, UI,
tests, and operating instructions agree with the frozen contract.

## Work and file ownership

- Integrate prerequisite branches in dependency order. Review conflict resolutions
  in requirements, imports, router/script registration, and migration numbering.
  Preserve unrelated user changes and earlier schema versions.
- Verify Python conventions, mapped classes for all tables, query construction,
  cleanup, domain/HTTP separation, and absence of scheduler startup in FastAPI.
- Reconcile code with contract fixtures, actual configuration, UI wording,
  dependency versions, deployment commands, and known runtime limitations.
- Perform the documented upgrade and rollback rehearsal on disposable copies;
  verify preexisting applications, settings, documents, preferences, and jobs.
- Run full release checks from the execution guide and the integration suite.
  Review visual/browser evidence from SCH-08/SCH-10 and verify outstanding fixes.
- Update ticket statuses and the roadmap only when acceptance evidence exists.
  Add final results to `docs/roadmap_scheduler/verification.md`, including any
  deferred work and manual live checks that were not performed.

## Acceptance and validation

All roadmap release criteria pass. The worker runs with FastAPI stopped and
recovers across restart; schedule edits persist; duplicate workers/claims are
prevented; UI and manual fetching still work; and upgrade/restore procedures are
reproducible. No live scraping is necessary for automated acceptance.

A remaining blocker keeps this ticket pending; a passing test suite alone does
not waive migration, process isolation, or UI acceptance. Deliver the code and
launch instructions without installing a startup task or enabling production
schedules as an incidental integration step.

**Handoff:** concise release summary, changed areas, verified outcomes, known
limits, and user-operable launch/stop instructions.
