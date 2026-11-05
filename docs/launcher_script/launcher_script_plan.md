# Launcher script implementation plan

Status: planning only; no launcher implementation yet.

## Scope and proposed defaults

- Manage `web` (Uvicorn running `app.main:app`) and `scheduler`
  (`python -m app.scheduler`). These are the two application services described
  in the README; assume the Jira coding agent and LM Studio are outside scope.
- Support Windows locally and Linux inside Docker. Use the selected Python
  environment, resolve paths from the repository root, and pass the same
  database and lock settings to both services.
- Provide mutually exclusive `-start`, `-stop`, `-restart`, and `-status` flags,
  with double-dash aliases. Require `--service NAME` or `--all` for mutations;
  status defaults to all registered services, including stopped services.
- Local starts run in the background and return after startup verification.
  Disable Uvicorn reload by default. Repeated start/stop requests are harmless.
- Status reports process state separately from readiness/health, with a PID
  where available. Scheduler health must remain readable when the web is stopped.

Example proposed commands:

```text
python launcher.py -start --service web
python launcher.py -stop --service scheduler
python launcher.py -restart --all
python launcher.py -status
```

## Implementation steps

1. **Define the CLI and service registry.** Add a thin root launcher entry point,
   a service definition model, a base process-controller class, platform-specific
   controllers, and a coordinating manager. Keep commands, environment settings,
   health checks, and optional dependencies in service definitions so additional
   services do not require new CLI branches. Follow repository Python conventions,
   including descriptive names, docstrings, and `C_` constants.
2. **Implement safe process ownership.** Serialize concurrent lifecycle commands;
   store per-service process identity and startup metadata in a runtime directory.
   Verify identity before stopping, handle stale records and port conflicts, and
   track child processes. Do not adopt or terminate unrelated Python processes.
3. **Implement lifecycle operations.** Validate the environment, start services,
   and wait for bounded readiness checks. Stop gracefully, allowing the scheduler
   the documented 120-second grace period. Use a Windows-compatible cooperative
   shutdown mechanism; ordinary process termination is not graceful there.
   Propose explicit `--force` for termination after timeout. Restart starts only
   after stop succeeds. For `--all`, respect dependency order, report every result,
   and return nonzero on any failure; retain services successfully started.
4. **Add status and diagnostics.** Distinguish stopped, starting, running,
   unhealthy, and unknown states. Reuse existing scheduler health data through its
   repository layer and provide a web readiness check. Keep status read-only.
   Capture startup errors and child output while retaining existing service logs.
5. **Implement the agreed Docker lifecycle.** If the launcher runs inside a
   container, add a foreground mode that forwards shutdown requests, reaps child
   processes, and exits on an unexpected required-service failure. Define whether
   one or both services run per container, how control commands reach the active
   supervisor, and how database/lock volumes are shared. Configure web binding for
   container access. Host-side Docker/Compose management is a separate scope choice.
6. **Verify and document.** Test single/all-service operations, duplicate and
   concurrent commands, stale/reused PIDs, failed startup, shutdown timeout, child
   cleanup, and scheduler independence using disposable data and test processes.
   Smoke-test Windows and the agreed Linux container setup. Document commands,
   configuration, logs, exit codes, and compatibility with `Start-Scheduler.ps1`.

## Decisions to clarify before implementation

1. **Service scope:** Are the initial services the web server and job-search
   scheduler, excluding the Jira coding agent and LM Studio?
2. **Docker topology:** Should the script run inside one container containing both
   services, inside separate containers, or manage Docker containers from the host?
   Should this task also supply a Dockerfile and/or Compose configuration?
3. **Local lifecycle:** Is background startup with explicit stop/restart commands
   the intended default, or should startup keep the terminal attached?

Other behavior above is proposed rather than explicitly required by the specs,
particularly health reporting, force-stop policy, and partial-failure handling.
