# Scheduler coding-agent execution guide

This guide is for future implementation. The current deliverable is documentation
only. Each [roadmap](scheduler_roadmap.md) ticket is one reviewable assignment.

## Preparation

Read the repository's [AGENTS.md](../../AGENTS.md), the roadmap, the assigned
ticket, and prerequisite handoffs. Reinspect the current code before changing it.
SCH-01 freezes contracts first; dependent agents must not invent competing
payloads, lifecycle states, paths, or error mappings.

Use the CV Builder project root as the working directory, not this documentation
folder. Give each simultaneously editing agent a separate branch and isolated
checkout/worktree. Suggested branch names: `codex/scheduler-sch-02`, etc. Create
those workspaces using the host's supported worktree facility. A single shared
checkout is suitable only for sequential implementation. No worktrees or agents
are created by this planning deliverable.

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
Mark a task complete only after its acceptance checks pass. Keep ticket status
and the roadmap synchronized during implementation; all tickets are pending now.

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
