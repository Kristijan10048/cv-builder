# Launcher script implementation plan

Status: base launcher implemented; see [usage and verification](launcher_usage.md).
The terminal appearance update below is proposed and awaiting plan approval.
The earlier implementation authorization applies to the base launcher only.

## Terminal appearance update - 2026-11-17 (proposed)

Implement the terminal-look requirements from
[the updated specifications](launcher_script_specs.md) as an extension of the
existing shared output layer. This section is the current work plan; the earlier
sections below retain the base launcher design and verification history.
No application implementation is part of this planning update.

### Proposed behavior

- **Commit title:** Show `CV Builder Launcher | commit <short HEAD hash>` once
  before command results. Also set the terminal window/tab title to this text
  when the terminal supports it. This covers both interpretations of "title";
  the visible header remains useful when the terminal controls its own tab title.
  Resolve the checked-out repository's HEAD, independent of the caller's working
  directory, with a bounded, read-only Git command. Use Git's short hash (normally
  seven or more characters). This identifies the current checkout, not necessarily
  the revision used by an already-running service.
- **Missing Git metadata:** Display `commit unavailable` if Git is missing, HEAD
  cannot be resolved, or the lookup times out. Continue the requested operation.
  Docker compatibility must not depend on Git or a `.git` directory being shipped
  in the image; adding build-time revision metadata is outside this update.
- **Generic status colors:** Use one mapping shared by all registered services
  and commands, including future services. Keep readable labels alongside color.
  Apply color to the label only, retaining the existing aligned columns and detail
  text. Keep process state separate from health.

| Label / outcome | Proposed color | Meaning |
| --- | --- | --- |
| `stopped` | Yellow | Service is stopped. |
| `running` | Green | Service is running; health remains a separate column. |
| `failed to start` | Red | The current start attempt failed, including the start phase of restart. |
| `starting`, `stopping` | Default terminal color | Transitional process states. |
| `unhealthy`, `unknown`, other labels | Default terminal color | Preserve existing state and health distinctions. |

- **Failure semantics:** `failed to start` is an operation-result label, not a new
  persisted process state. Display it immediately with the existing diagnostic
  detail. A later status command reports the actual observed state, which may be
  stopped or still starting after a readiness timeout. Do not infer success or
  failure by matching message text. Stop failures must not be labelled as startup
  failures. Retain current exit codes, partial-success behavior, and diagnostics.
- **Terminal compatibility:** Enable color and title control only on supported
  interactive terminals, with Windows and Linux handling behind a shared terminal
  capability abstraction. Respect `NO_COLOR` for colors and `TERM=dumb` for
  terminal styling/control. Detect the actual destination independently for stdout
  and stderr. Redirected output and container logs retain the plain-text header
  and labels, with no ANSI color or title-control sequences. Unsupported terminals
  fall back to readable plain text without failing the command.
- **Output flow:** Print the header after argument validation and before executing
  a valid command. Preserve standard argument-parser help and syntax errors,
  immediate lifecycle progress, both restart phases, and foreground messages.
  No screen clearing, animated dashboard, or continuous refresh is required.

### Graphical CLI preview

Illustrative rendered preview of `python launcher.py -status`:

> **CV Builder Launcher | commit a1b2c3d**

| Service | State | Health | PID | Details |
| --- | --- | --- | --- | --- |
| web | 🟢 **running** | healthy | 14280 | Ready |
| scheduler | 🟡 **stopped** | unavailable | - | not running under this launcher |

Illustrative startup failure from `python launcher.py -start --service scheduler`:

> **CV Builder Launcher | commit a1b2c3d**
>
> scheduler: 🔴 **failed to start**; startup failed; inspect &lt;launcher log path&gt;

The colored markers represent colored label text in the real terminal; emoji and
Markdown table borders will not be emitted. The actual CLI retains its existing
aligned row layout and separators. The hash, PID, and readiness detail above are
illustrative. The terminal window/tab title matches the visible header where
supported. With styling disabled, the same words and alignment remain readable.

### Implementation steps after approval

1. **Add commit-title support.** Introduce an injectable revision provider and
   terminal capability adapter with base interfaces. Resolve HEAD once per CLI
   invocation from the repository root with a timeout and graceful fallback.
   Route header/title rendering through `LauncherOutput`; keep the Git lookup
   independent of service management and database access.
2. **Extend shared formatting.** Extend `app/launcher/output.py` with semantic
   label styling and a generic color mapping. Calculate column widths and padding
   using unstyled text, then apply/reset color around labels so escape sequences
   cannot change alignment or leak color into following output. Keep custom row
   templates and longer future service names supported. Centralize new strings,
   style codes, and timeout values as `C_` constants and document new classes and
   functions in line with the repository conventions.
3. **Connect command outcomes.** Have `app/launcher/manager.py` pass explicit
   operation outcomes to the shared writer for start, stop, restart, and foreground
   results. Preserve diagnostic details and distinguish failed startup from other
   errors. Integrate the once-per-command header in `app/launcher/cli.py`; status
   continues using the existing `ServiceStatus` process and health fields.
4. **Verify and document.** Extend `tests/test_launcher.py` to cover the three
   required colors, plain-text fallbacks, stdout/stderr capability differences,
   `NO_COLOR`, `TERM=dumb`, title support, missing Git/HEAD and lookup timeout,
   invocation from another directory, ANSI-safe column alignment, and an extra
   service with a longer name. Cover failed start/restart and verify that later
   status still reflects actual process state. Run the launcher regression suite;
   visually check supported Windows and Linux terminals where available and record
   verification limits. Update `launcher_usage.md` with examples and fallbacks.

### Acceptance criteria

- Every valid command displays the current checkout's abbreviated commit hash
  (or the documented fallback), with a matching terminal title where supported.
- Stopped labels are yellow, running labels green, and failed-start labels red
  in supported interactive terminals across all services without service-specific
  formatting branches.
- Styling preserves column alignment, readable diagnostics, immediate progress,
  process/health distinctions, and existing lifecycle behavior.
- Redirected output has no terminal control sequences; missing Git and unsupported
  styling never prevent service operations.
- Review and approve this proposed update before implementation. The historical
  test results below are evidence for the base launcher only, not this update.

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

## Implementation authorization and defaults — 2026-11-05

The user confirmed the remaining defaults and authorized implementation:

- Allow up to 120 seconds for graceful shutdown, with explicit `--force` required
  for termination after timeout.
- Show all services, including stopped ones, and distinguish process state from
  application health.
- Keep successful services running after a partial startup failure and report
  failures with a nonzero exit code.

The implementation adds `launcher.py`, reusable modules in `app/launcher`, offline
lifecycle tests, and usage documentation. Docker image and Compose work remain
outside scope. Linux/container integration verification requires a suitable
environment and is recorded separately from Windows verification.

## Verification record — 2026-11-05

- Launcher suite: 33 tests passed on Windows, including real service subprocesses
  using disposable databases and paths containing spaces.
- Full repository suite: 413 tests and 59 subtests passed; one existing
  `powershell.exe` scheduler-launcher test was blocked by the host's unsigned-script
  execution policy. No machine execution-policy settings were changed.
- JavaScript syntax checks and Git whitespace checks passed.
- WSL is not installed on this host. Linux process options are covered by tests,
  but an actual Linux/container smoke test has not been performed.

## Status formatting requirement — 2026-11-05

Display status rows with vertically aligned columns for service name, state,
health, PID, and details. Size each column from the widest value in the displayed
snapshot so alignment is preserved for different states, PID lengths, and future
service names. Apply this formatting to both `-status` and `--status`.

```text
web      : stopped; health=unavailable; pid=-; not running under this launcher
scheduler: stopped; health=unavailable; pid=-; not running under this launcher
```

## Shared command formatting — 2026-11-05

Extend vertical alignment to all launcher command results: start, stop, restart,
status, foreground service messages, and errors. Preserve immediate lifecycle
progress output and both phases of restart. Reserve a common service-name width
from the registry before streaming results; size additional status columns from
the displayed snapshot. Command-wide errors use an aligned `launcher` label on
stderr; command syntax/help retains the argument parser's standard layout.

Centralize formatting in `app/launcher/output.py`, with a `BaseOutputFormatter`
interface, generic `AlignedOutputFormatter`, and shared `LauncherOutput` writer.
Future commands reuse named row values, templates, and calculated column widths
instead of duplicating formatting code. Both the CLI and service manager use this
writer. See the usage guide's extension section for the reuse contract and examples.

Verification: all 33 launcher tests passed after the shared-output refactor.
Manually checked start, stop, restart, mixed success/failure messages, mixed
status values, a longer future service name, and custom command columns without
starting application services during the formatting checks.

## Plan update - 2026-11-17 10:38:21 +01:00 (Europe/Berlin)

Status: proposed; awaiting review before implementation.

The latest [specifications](launcher_script_specs.md) add documentation requirements
to the terminal appearance update. The implementation steps and behavior proposed
above remain applicable, with these clarifications:

- Append future plan updates at the bottom of this file whenever possible,
  preserving earlier decisions and verification history. Include a timestamp with
  the timezone in each update. If a later decision replaces an earlier one,
  identify the superseded requirement explicitly in the appended update.
- Print the current Git commit hash in the visible CLI header, as well as the
  terminal title where supported. The preview must show that printed header;
  updating only the window/tab title does not meet this requirement.
- Retain the shared service-independent colors: yellow for stopped, green for
  running, and red for a failed start. Keep the previously proposed plain-text
  fallback and `commit unavailable` behavior.

### Updated graphical CLI preview

Example command: `python launcher.py -status`

> **CV Builder Launcher | commit a1b2c3d**

| Service | Status label | Label color | Health | PID | Details |
| --- | --- | --- | --- | --- | --- |
| web | **running** | Green | healthy | 14280 | Ready |
| scheduler | **stopped** | Yellow | unavailable | - | not running under this launcher |

Example command: `python launcher.py -start --service scheduler`

> **CV Builder Launcher | commit a1b2c3d**

| Service | Result label | Label color | Details |
| --- | --- | --- | --- |
| scheduler | **failed to start** | Red | startup failed; inspect &lt;launcher log path&gt; |

The header above is printed terminal output. The hash `a1b2c3d`, PID, and readiness
detail are illustrative; implementation resolves the actual current HEAD once per
invocation. The preview's color column describes the label styling and is not an
additional CLI column. Actual output retains the existing aligned row layout;
Markdown table borders are for this document only.

### Additional verification

- Verify that the printed header contains the resolved commit hash even when
  terminal title control is unsupported or output is redirected.
- Keep future plan updates timestamped and appended at the bottom where possible.
- This update changes documentation only and does not authorize implementation.

## Implementation and verification - 2026-11-17 10:52:43 +01:00 (Europe/Berlin)

Status: terminal appearance update implemented following the user's approval.
This entry supersedes the earlier "awaiting review" status and planning-only
restriction for the terminal appearance update. Earlier records remain historical.

- Added a bounded Git revision provider and terminal capability interfaces in
  `app/launcher/presentation.py`. The CLI prints the checkout hash once per valid
  invocation and sets the terminal title where supported. Missing Git/HEAD and
  lookup failures use `commit unavailable` without blocking service operations.
- Extended the shared output formatter with green running, yellow stopped, and
  red failed-start text. Visible text determines status-column widths before ANSI
  styling. Lifecycle operations pass explicit outcomes, including foreground
  startup failures and cleanup results; later status still reports actual state.
- Preserved the existing aligned output layout. As clarified during review,
  "Status label" and "Label color" are explanatory preview headings only and
  are not emitted by the CLI.
- Added stream-specific terminal detection, Windows virtual-terminal support,
  `NO_COLOR` and `TERM=dumb` handling, and plain output for redirected logs.
  Updated `launcher_usage.md` with behavior, examples, and extension guidance.

Verification:

- Final run of `python -m pytest tests/test_launcher.py -q -k
  'not TestActualServiceProcesses and not TestControlProtocol'`: **51 passed,
  7 deselected**. Coverage includes revision fallback/timeout, a real CLI call
  from another working directory, status alignment, generic service colors,
  independent output streams, terminal opt-outs, and start/restart/foreground
  failure semantics.
- The full launcher suite was also attempted: **7 failures** in the local HTTP
  control and real-service integration tests. The control test reports Windows
  socket access denied (`WinError 10013`), reproduced in isolation; the six
  real-service tests fail startup/readiness checks or time out. End-to-end
  lifecycle verification remains incomplete in this restricted environment.
  Rerun `python -m pytest tests/test_launcher.py -q` where local socket connections
  are permitted. Do not treat the earlier historical green suite as verification
  of this implementation.
- Git whitespace checks passed. Actual visual checks in Windows/Linux terminal
  windows and Linux/container integration were not performed; terminal decoration
  was verified through automated output and capability tests.
