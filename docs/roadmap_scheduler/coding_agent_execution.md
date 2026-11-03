# Scheduler coding-agent execution guide

The original guide below describes the planned multi-branch implementation.
On 2026-11-03 the user requested a single implementation pass; all tickets were
completed sequentially on the existing `Implement_scheduler` branch without
creating agents, branches, commits or merges. See [verification.md](verification.md)
for the delivered code, commands and evidence. The instructions below are retained
as historical planning guidance rather than a request to redo completed work.

## Preparation

Read the repository's [AGENTS.md](../../AGENTS.md), the roadmap, the assigned
ticket, and prerequisite handoffs. Reinspect the current code before changing it.
SCH-01 freezes contracts first; dependent agents must not invent competing
payloads, lifecycle states, paths, or error mappings.

Use the CV Builder project root as the working directory, not this documentation
folder. Give each simultaneously editing agent a separate branch and isolated
checkout/worktree. Use the required ticket branch names described below. Create
those workspaces using the host's supported worktree facility. A single shared
checkout is suitable only for sequential implementation. No worktrees or agents
are created by this planning deliverable.

## Branch workflow

Before starting implementation of any scheduler ticket, create and switch to a
new branch using `SCH-XX_<Ticket_description>`. Each ticket's **Implementation
branch** section specifies its exact name. Keep the uppercase ticket ID and use
underscores between description words, with no spaces or `codex/` prefix.
For example, SCH-02 uses `SCH-02_Extract_the_reusable_job_fetch_backend`.

Before creating and checking out a new ticket branch, verify that the current
branch is `master` and the working tree is clean: no staged, unstaged, or
untracked changes. All completed prerequisites must already be merged into
`master`; do not branch from another implementation branch.

Check with `git branch --show-current` and `git status --porcelain=v1 --untracked-files=all`.
The first command must report `master`, and the second must return no entries.
If either check fails, stop branch creation and resolve the condition without
discarding changes or automatically committing or stashing them. Recheck both
conditions immediately before creating the branch.

When using an isolated worktree, perform these checks in the source checkout,
then create the worktree on the ticket's required new branch from `master`
through the host's supported worktree facility. Otherwise, create and switch
to the branch from the verified clean `master` checkout before editing.
Keep one ticket's implementation per branch and report the exact name in its
handoff.

If that branch already exists because the ticket is being resumed, inspect it
and continue the existing ticket work on that branch; do not reset, overwrite,
or repurpose it. If the name belongs to unrelated work, resolve the collision
before implementation. This rule applies to future implementation work and does
not require renaming historical branches for completed tickets.

## Parallel assignments and file ownership

| Wave | Assignments that can overlap | Shared-file rule |
| --- | --- | --- |
| 1 | SCH-01 | Owns contracts, abstract interfaces, constants, dependency selection. |
| 2 | SCH-02 backend; SCH-03 storage; SCH-07 UI foundations | SCH-02 owns existing job-search code; SCH-03 owns database/migration infrastructure; SCH-07 owns navigation/utilities. |
| 3 | SCH-04 runtime; SCH-05 handler; SCH-06 API; SCH-08 UI feature | SCH-04 owns runtime; SCH-05 owns board guard; SCH-06 alone wires app.main and preference deletion; SCH-08 alone wires index.html after SCH-07. |
| 4 | SCH-09 | Integrates runtime and handler; earlier owners have finished. |
| 5 | SCH-10 verification; SCH-11 operations | Tests and docs/scripts are separate; product fixes go back to the owning ticket. |
| 6 | SCH-12 | Integrates, resolves shared-file conflicts, and verifies the full release. |

SCH-03 owns new scheduler mappings in `app/scheduler/database_models.py` using
the existing `DatabaseModel` base; avoid parallel changes to
`app/database_models.py`. SCH-01 owns public interfaces in
`app/scheduler/contracts.py`; later agents request amendments rather than
independently changing signatures. SCH-03 assigns/registers migration versions.
SCH-07 completes changes to `static/app.js` and `templates/index.html` before
SCH-08 integrates the new screen. SCH-02 finishes preference repository seams
before SCH-06 adds deletion rules.

File targets in tickets are proposed implementation outputs, not existing files.
Ticket-local tests may be added alongside code; SCH-10 alone owns the shared
cross-process test harness. Avoid editing the global test fixture in parallel.

SCH-08 intentionally depends on the frozen API contract and UI foundation, not
the implemented API. Use the contract fixtures for development and acceptance of
that ticket; SCH-10 is the mandatory live API/UI integration gate. Similarly,
SCH-04 uses a fake handler until SCH-09 integrates SCH-05.

## Assignment prompt

Paste this into a coding agent such as Codex CLI, substituting the ticket ID:

> Implement docs/roadmap_scheduler/tickets/SCH-XX.md in this isolated checkout.
> Read AGENTS.md, scheduler_roadmap.md, and coding_agent_execution.md first.
> Before creating and checking out a new branch, verify the current branch is master
> and the working tree is clean, with no staged, unstaged, or untracked changes.
> Completed prerequisites must already be merged into master. If either check fails,
> stop branch creation; do not discard, automatically commit, or stash changes.
> Then create and switch from master to the exact SCH-XX_<Ticket_description>
> branch named in the ticket. If resuming
> that ticket's existing branch, inspect and reuse it without resetting it.
> Verify prerequisite implementations and their checks before editing. Preserve
> unrelated changes. Follow the agreed contracts and own only the ticket's file
> targets; propose shared-interface changes for integration instead of silently
> diverging. Use temporary databases, offline fixtures, and fake job boards.
> Complete acceptance checks and report files changed, checks actually run,
> outcomes, limitations, and downstream handoff details. Do not start production
> workers, register OS startup tasks, or access real job boards during tests.

This prompt does not require a specific CLI flag or agent model. The coordinator
may assign a ready ticket to any available coding agent and queue excess tickets
when concurrency is limited.

## Handoffs and integration

Each handoff includes the branch/change reference, prerequisite versions,
changed paths, interface changes, migration version if applicable, test commands
and outcomes, unresolved criteria, and fixtures downstream tasks can reuse.
Mark a task complete only after its acceptance checks pass. All scheduler tickets
are now complete; their integrated acceptance is recorded in verification.md.

Integrate in dependency order. Run focused tests after each merge; run the full
suite at SCH-12. Shared-file conflicts require a semantic review of both changes,
not accepting one side wholesale. Discovering an interface defect reopens the
owning ticket and blocks affected dependents until the contract is updated.

Proposed release checks, from the project root after implementation:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
node --test tests/theme.test.cjs tests/ui_core.test.cjs tests/scheduled_tasks.test.cjs
node --check static/app.js
node --check static/ui_core.js
node --check static/scheduled_tasks.js
```

These are future checks; the new paths do not exist yet. Add any other changed
JavaScript files to syntax checking. Do not install scheduler dependencies into
`coding_agent/jira_agent` or launch its automation to validate this service.

The existing `tests/conftest.py` patches database paths only within its Python
process. Every spawned test process must receive its own explicit temporary
database, lock, and log paths before importing application modules. A monkeypatch
in the parent is not enough. The harness must fail closed if isolation settings
are missing, and stop only processes that it created.
