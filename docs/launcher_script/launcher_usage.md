# Application service launcher

`launcher.py` manages the web server (`web`) and job-search scheduler
(`scheduler`). It uses the Python interpreter that invokes it and the existing
`CV_BUILDER_*` application settings. Install `requirements.txt` in that environment
first; process identity checks use the pinned `psutil` dependency.

## Commands

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe launcher.py -start --all
.\.venv\Scripts\python.exe launcher.py -status
.\.venv\Scripts\python.exe launcher.py -restart --service web
.\.venv\Scripts\python.exe launcher.py -stop --service scheduler
.\.venv\Scripts\python.exe launcher.py -stop --all
```

On Linux, use the selected environment's `python launcher.py` with the same flags.
An absolute path to `launcher.py` works from any working directory. Each action
also accepts a double-dash alias, such as `--start` or `--status`.

- Start, stop, and restart require `--service NAME` or `--all`.
- Status defaults to all registered services, including stopped services, and can
  be restricted with `--service NAME`.
- Local startup creates hidden background processes and returns after checking
  readiness. Closing the terminal does not stop them. Uvicorn reload is disabled.
- Starting a healthy running service or stopping a stopped service succeeds
  without changing its identity. Restart waits for successful shutdown before
  launching a replacement.
- A partial `--all` startup reports failures and keeps successful services running.
  If readiness times out, a still-starting process is retained for status/stop;
  inspect its launcher log before retrying.
- Exit codes: `0` for successful operations/status of running or stopped services;
  `1` for lifecycle failure or starting/stopping/unhealthy/unknown status; `2` for
  invalid command syntax.

## Shutdown and ownership

Stop requests use a secret-protected loopback endpoint and the service's normal
shutdown path, including on Windows. The scheduler stops taking new work and
waits for active searches. Allow up to 120 seconds by default. A timeout returns
failure and leaves the process under management. To permit forced termination
after the grace period:

```powershell
.\.venv\Scripts\python.exe launcher.py -stop --service scheduler --force
```

`--force` is also accepted with restart. Force kills the verified process tree;
interrupted scheduler work follows the existing recovery rules in the
[scheduler guide](../scheduler_operations.md). A subsequent force command allows
another grace period before killing. Without force, an unreachable control
endpoint reports failure immediately because graceful shutdown could not be
requested.

The launcher only controls its own instances. It verifies the PID, process birth
time, runner command, and launch identifier. An old or reused PID is treated as
stopped and never targeted. Corrupt state or denied access reports unknown and
blocks mutations; inspect the state and process before changing files manually.
Do not delete runtime files while a service is alive.

Services started with Uvicorn, `python -m app.scheduler`, or
`scripts/Start-Scheduler.ps1` remain supported independently. Stop them through
their original launch mechanism before switching to this launcher. Port conflicts
and scheduler singleton locking prevent accidental duplicate application instances;
the launcher does not adopt or stop manually launched processes.

## Configuration and diagnostics

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `CV_BUILDER_WEB_HOST` | `127.0.0.1` | Web bind address; configurable for future container use. |
| `CV_BUILDER_WEB_PORT` | `8000` | Web listen port, from 1 to 65535. |
| `CV_BUILDER_LAUNCHER_STATE_DIR` | `<lock directory>/launcher/<database identity>` | Private process records, locks, and captured console output. |
| `CV_BUILDER_LAUNCHER_START_TIMEOUT` | `30` | Positive finite readiness timeout in seconds per service. |
| `CV_BUILDER_LAUNCHER_STOP_TIMEOUT` | `120` | Positive finite shutdown grace period in seconds per service. |

Relative paths resolve from the repository root. The database and lock settings
are inherited by both services; use the same settings for subsequent commands.
When using a custom state directory, dedicate it to one application instance.
Lifecycle commands are serialized; a competing command that cannot acquire the
lock within five seconds reports failure and can be retried.

`web.launcher.log` and `scheduler.launcher.log` in the state directory capture
startup errors and console output. These files append and do not rotate; remove
or archive them only while the corresponding service is stopped. Existing
rotating application logs remain in their configured locations. State records
contain local control credentials: keep this directory private.

Status distinguishes process state from health. Web readiness checks completed
Uvicorn startup and an HTTP response; scheduler health reads its heartbeat through
a read-only database connection, independently of the web server. Status does not
create/migrate the database or change process records. A stopped result means no
verified launcher-owned process, not proof that no manually started app exists.

## Foreground supervision and future Docker compatibility

```text
python launcher.py -start --all --foreground
python launcher.py -start --service scheduler --foreground
```

Foreground mode requires the selected services to be stopped initially. It stays
alive as their supervisor, reaps exited children, and handles SIGINT/SIGTERM by
requesting graceful shutdown. Commands from another terminal can stop or restart
managed services; intentional restarts preserve the supervisor. Stopping all
selected services exits successfully. An unexpected process exit shuts down the
remaining selected services and returns failure. Shutdown timeouts are reported as
failure; supervision does not implicitly force-kill active work.

This mode is suitable for a future container entry point. Dockerfiles, images,
Compose configuration, volume setup, and deployment are outside this task. The
planned initial topology is one container for both services; service selection
also supports future separation. No container packaging is created here.

## Extending and verifying

Add a `ServiceDefinition` and a `BaseServiceRuntime` implementation to the trusted
registry in `app/launcher/services.py`. The runtime supplies foreground execution,
cooperative stopping, and health checks. Optional dependencies define startup
order. The CLI and OS process controller do not need new service-specific branches.

Run the offline lifecycle tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_launcher.py -q
```

The tests launch real services against disposable databases and cover ownership,
authentication, duplicate/concurrent commands, port conflicts, independent worker
health, shutdown timeout/force behavior, and foreground restart/crash cleanup.
Windows process behavior is verified on the development host. Linux process
options are tested, but an actual Linux/container smoke test remains for an
environment providing Linux and the separate image task.
