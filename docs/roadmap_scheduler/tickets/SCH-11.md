# SCH-11: Document Windows startup, maintenance, and rollback

**Status:** Pending. **Depends on:** [SCH-09](SCH-09.md).
**Estimate:** 0.5–1 day.

[Roadmap](../scheduler_roadmap.md) | [Agent guide](../coding_agent_execution.md)

## Implementation branch

Before creating and checking out the new branch, verify that the current branch
is `master` and the working tree is clean: no staged, unstaged, or untracked
changes. The completed prerequisites must already be merged into `master`.
If either check fails, stop branch creation and resolve it without discarding
changes or automatically committing or stashing them.

Once these checks pass, create and switch from `master` to a new branch named
`SCH-11_Document_Windows_startup_maintenance_and_rollback`.
This follows the required `SCH-XX_<Ticket_description>` format. Keep this
ticket's implementation on that branch and include its name in the handoff.
Follow the [branch workflow](../coding_agent_execution.md#branch-workflow) when
resuming existing work or using an isolated worktree.

## Outcome

A user can launch and supervise the worker independently, diagnose missed work,
and upgrade or roll back without accidentally running duplicate workers.

## Work and file ownership

- Create `scripts/Start-Scheduler.ps1` and `docs/scheduler_operations.md`; update
  the root README with the implemented commands and link to the operations guide.
- Resolve the project/interpreter/database paths explicitly; validate dependencies
  and configuration and propagate nonzero exits. Provide foreground operation for
  diagnosis. Background launches must use hidden windows.
- Document optional Windows Task Scheduler setup at user logon, full working
  directory, environment configuration, restart-on-failure, no parallel instance,
  and how to stop the complete process tree. Do not register a task automatically.
- Explain that user-logon startup does not run before login and that a sleeping or
  powered-off computer cannot execute jobs. State catch-up and missed-run policy.
  True Windows service installation is a separate extension.
- Document dependency installation, supported runtime versions, worker status,
  schedule creation, log locations, lock contention, stale heartbeat, cooldown,
  retention, and bounded graceful-stop/forced-stop expectations.
- Explain stopped-process backup, disposable-copy migration rehearsal, and the
  matching-code/database restore required because older migration runners reject
  new schema versions. Call out loss of post-backup changes on restore.
- Include a troubleshooting distinction between “no jobs matched,” “partial
  board failure,” “worker offline,” and “request queued but not executed.”

## Acceptance and validation

Validate the launcher with a disposable fake-handler setup, including paths with
spaces, missing environment, duplicate startup, normal stop, and failing startup.
Follow the README from a clean test environment. Do not install a persistent OS
task or start scraping the user's real saved searches during verification.

**Handoff:** tested launch instructions, exact version/configuration requirements,
maintenance and rollback procedure, and limits of user-session startup.
