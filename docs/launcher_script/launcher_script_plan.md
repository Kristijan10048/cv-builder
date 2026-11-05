# Launcher script implementation plan

Status: planning only; no launcher implementation yet.

## Scope and proposed defaults

- Manage `web` (Uvicorn running `app.main:app`) and `scheduler`
  (`python -m app.scheduler`). These are the confirmed initial services.
  Other test applications/services, including the Jira coding agent, are omitted
  for now; LM Studio is outside launcher scope.
- Keep the launcher compatible with the planned single Docker container running
  both services. Keep service definitions independent for future separation.
- Docker image creation, Dockerfiles, Compose configuration, container deployment,
  and unrelated changes are outside scope and belong to a separate task.
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
5. **Keep the launcher Docker-compatible.** Support Linux process control,
   configurable paths and web binding, and shared database/lock settings. Provide
   a foreground supervision mode suitable for a future container entry point,
   with shutdown forwarding and child-process reaping, alongside local background
   startup. Keep service selection configurable for future separation. Container
   packaging, volumes, detached deployment, and host-side container lifecycle
   commands belong to the separate Docker task.
6. **Verify and document.** Test single/all-service operations, duplicate and
   concurrent commands, stale/reused PIDs, failed startup, shutdown timeout, child
   cleanup, and scheduler independence using disposable data and test processes.
   Smoke-test Windows and Linux launcher behavior where available; record any
   platform verification limits. End-to-end image/Compose validation belongs to
   the separate Docker task. Document launcher commands, configuration, logs,
   exit codes, and compatibility with `Start-Scheduler.ps1`.

## Original clarification questions

The questions below are retained for context; answers are recorded at the end.

1. **Service scope:** Are the initial services the web server and job-search
   scheduler, excluding the Jira coding agent and LM Studio?
2. **Docker topology:** Should the script run inside one container containing both
   services, inside separate containers, or manage Docker containers from the host?
   Should this task also supply a Dockerfile and/or Compose configuration?
3. **Local lifecycle:** Is background startup with explicit stop/restart commands
   the intended default, or should startup keep the terminal attached?

Other behavior above is proposed rather than explicitly required by the specs,
particularly health reporting, force-stop policy, and partial-failure handling.

## Confirmed answers — 2026-11-05

1. **Service scope:** Yes, manage only the scheduler and web server for now.
   Omit other test applications/services, such as the Jira coding agent.
2. **Docker topology:** Keep the initial setup simple: place both services in a
   single Docker container. They may be separated into containers in the future.
3. **Background operation:** Yes, services should run in the background.
   Local startup returns control to the terminal. Future Docker deployment can
   run detached with an active supervisor inside; deployment is a separate task.

## Scope clarification — 2026-11-05

Docker Compose, Docker image implementation, and other unrelated changes are
outside this task. Image and Compose work will be implemented in a separate task.
This plan covers the launcher and its Docker compatibility only; Docker packaging
is no longer an open deliverable question for this task.
