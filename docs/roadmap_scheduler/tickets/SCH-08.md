# SCH-08: Build the Scheduled Tasks screen

**Status:** Complete (2026-11-03). **Depends on:** [SCH-07](SCH-07.md).
**Estimate:** 1.5–2.5 days.

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
`SCH-08_Build_the_Scheduled_Tasks_screen`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

Users can configure schedules and understand worker status, upcoming runs, and
past outcomes through the existing CV Builder interface.

## Work and file ownership

- Create `static/scheduled_tasks.js`, `static/scheduled_tasks.css`, and
  `templates/scheduled_tasks.html`; wire the page/navigation in
  `templates/index.html`, using SCH-07 registration instead of new global branches.
- Use SCH-01 API fixtures while SCH-06 is in progress. No live API dependency is
  needed to build the page; final integration is mandatory in SCH-10.
- Implement create/edit forms for saved search, boards, result limit, name,
  interval or once, and future start. Convert user input to offset-bearing UTC
  dates and display the applicable timezone. Explain elapsed-time intervals.
- List next run and last result, plus pause/resume, run now, deletion confirmation,
  and paginated history. Reuse a request key on run-now retry until the response
  is known. Show revision conflicts with refresh/reload guidance.
- Poll worker health and active runs only while the page is visible; cancel on
  leave, ignore stale responses, and avoid duplicate listeners on re-entry.
- Distinguish saved/queued/running/completed, offline worker, partial failure,
  missed and interrupted runs. Show board warnings and no-saved-search guidance.
  Explain that deleting or pausing cannot stop already-running work.
- Escape all user/source text. Preserve focus, labels, keyboard access, mobile
  usability, and both themes; do not expose scheduler internals in user copy.

## Acceptance and validation

Create/run `tests/scheduled_tasks.test.cjs` with contract fixtures. Cover form
validation, timezone serialization, lifecycle cleanup, double-click/run-now retry,
stale response suppression, conflicts, offline state, and history pagination.

Syntax-check both new and changed scripts and run theme regressions. Review the
page visually in light/dark and narrow/wide layouts using disposable data. Record
screenshots or a concise visual checklist. Live API compatibility is a SCH-10
release gate even if this fixture-driven ticket passes.

**Handoff:** page assets, fixture-driven checks, visible-state coverage, and any
contract discrepancies for SCH-06 to resolve before integration.
