# Running the scheduler

The web application saves schedule definitions. A separate worker executes them,
including when the web server and browser are closed. This is a single-machine,
local-disk deployment. Do not use network shares, multiple hosts, or different
aliases/hard links for the same database.

## First start

From the repository root, use the existing application virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\Start-Scheduler.ps1 -ValidateOnly
.\scripts\Start-Scheduler.ps1
```

The equivalent foreground command is:

```powershell
.\.venv\Scripts\python.exe -m app.scheduler
```

If your PowerShell execution policy blocks `.ps1` scripts, use the direct Python
command. No execution-policy change is required. The launcher was validated with
PowerShell 7.6.5; the machine's Windows PowerShell 5 host blocks unsigned scripts.

The application dependencies pin APScheduler 3.11.3 and portalocker 4.4.2. The
implementation was verified on Windows x64 with Python 3.15.2. The existing
Python 3.14 setup instructions remain usable, but this release's verification
environment is recorded in the scheduler verification report.

Open **Scheduled Tasks**, choose **New schedule**, select a saved search and
boards, and choose an interval or one-time execution with a future first time.
Only select boards supported by the saved search's country. Schedules are enabled
when created. To stage a rollout, choose a sufficiently distant first time and
pause the schedule before starting the worker.

**Run now** accepts a durable request; “Queued” does not mean it has executed.
The request may run while its schedule is paused, without resuming it or changing
its next timed occurrence. A request expires after five minutes if not started.
The browser retries an uncertain run-now response with the same request key.

## Shared configuration

Set the same database and lock directory for **both** web and worker processes.
Relative paths resolve against the repository root, independent of working
directory. Canonical names override legacy `APPLYKIT_` aliases.

| Variable | Default |
| --- | --- |
| `CV_BUILDER_DATABASE_PATH` | `data/cv_builder.db` |
| `CV_BUILDER_LOCK_DIR` | `data/locks` |
| `CV_BUILDER_SCHEDULER_LOG_DIR` | `logs` |
| `CV_BUILDER_SCHEDULER_MAX_WORKERS` | `2` (1–32) |
| `CV_BUILDER_SCHEDULER_POLL_SECONDS` | `5` (1–10) |
| `CV_BUILDER_SCHEDULER_RETENTION_DAYS` | `90` (1–3650) |

`Start-Scheduler.ps1` also accepts `-DatabasePath`, `-LockDirectory`, and
`-LogDirectory`; it restores the calling process's overridden environment after
exit. Paths containing spaces are supported. `-ValidateOnly` checks configuration
and imports without migrating a database or starting a worker.

Different lock roots cannot coordinate. Never delete lock files to “unlock” a
running process: the open OS handle, not file presence, is ownership. A second
worker exits nonzero. Process exit releases its lock automatically. Web and worker
startup serialize migration 5 through a separate database-specific lock.

## Optional Windows Task Scheduler startup

No startup task is installed automatically. To run at user logon, create a task
in Windows Task Scheduler using the same user account as the web application:

1. Trigger: **At log on** for that user. This does not run before login.
2. Program: the absolute path to `.venv\Scripts\python.exe`.
3. Arguments: `-m app.scheduler`; **Start in**: the absolute repository directory.
4. Supply the shared environment settings through the launching user's environment
   or a locally maintained launcher. Task Scheduler does not inherit temporary
   variables from an unrelated PowerShell window.
5. Configure restart on failure, for example after one minute, at most three
   attempts. Choose **Do not start a new instance** if already running. OS locking
   still protects against accidental starts outside Task Scheduler.
6. Choose your intended battery/sleep policy. A sleeping or powered-off machine
   cannot execute jobs. A true Windows service and execution before login are
   outside this release.

For an explicitly background PowerShell launch, use `Start-Process` with
`-WindowStyle Hidden`, the full interpreter path, `-ArgumentList '-m app.scheduler'`,
and the full repository `-WorkingDirectory`. Save the returned PID (`-PassThru`)
so you can identify this worker; do not stop unrelated Python processes.

## Stop, recovery, and timing

Use **Ctrl+C** in a foreground worker for graceful shutdown. It stops new claims,
waits for ongoing searches, records stopped health, closes resources, then releases
singleton ownership. Pausing/deleting a schedule cannot stop already-running work.
Edits cancel queued old-revision work at its final start gate; running work keeps
its captured definition and effective search criteria.

Allow a supervisor grace period of **120 seconds** before deciding a worker is
hung. Python threads cannot cancel a blocked scraper. The pinned JobSpy transports
control their own request timeouts; the scheduler does not promise a hard search
deadline. If shutdown will not finish, end only the identified worker's complete
process tree (for example `taskkill /PID <verified-worker-pid> /T /F`). This is a
forced stop, not graceful cancellation. The next worker marks abandoned owned
executions **Interrupted** and never automatically retries them. Jobs may already
have been saved before the crash; examine stored results before requesting a new
run. Unowned manual requests survive restarts until their expiry.

Intervals remain anchored to their first UTC instant, not completion time. After
downtime the worker coalesces occurrences to the latest one. It runs it only when
at most five minutes late; otherwise it records one **Missed** summary and skipped
count. Active schedules record **Skipped overlap** for overlapping occurrences.
Capacity-full schedules remain due and are re-evaluated on the next tick. An
expired one-shot becomes disabled. Resume advances paused intervals without
replay; an overdue paused one-shot needs a new future time before resuming.

“Every 24 hours” measures elapsed time and can shift local clock time at daylight
saving changes. Daily/weekly calendar rules, cron, automatic retries and arbitrary
shell/Python tasks are not supported.

## Diagnostics and retention

The Scheduled Tasks page and `GET /api/scheduler/status` show:

- **Online/fresh:** successful dispatch progress within 30 seconds.
- **Not responding/stale:** registered worker without recent dispatch progress.
  Inspect `logs/scheduler.log`, filesystem permissions, and database contention.
- **Offline/stopped:** no worker registration, or graceful shutdown completed.
- **Succeeded, zero jobs:** boards completed without matching results.
- **Partial:** some results were saved, with warnings or unavailable boards.
- **Failed:** no successful board or an execution/storage failure; see history.
- **Queued:** accepted but not started; offline requests can expire.

Worker logs use `scheduler.log`, INFO, 5 MiB rotation and three backups, separate
from `cv_builder.log`. Only scheduler diagnostics go to this file; scraped job
descriptions and saved criteria are excluded. Board exclusion is nonblocking;
**busy** and **cooldown** warnings allow other boards to continue. A Glassdoor
HTTP 429 establishes a five-minute persisted cooldown shared by manual and
scheduled fetching, including across restarts.

Terminal history is pruned in batches of 100 after the configured retention period.
Active runs are never pruned. A retained manual key remains deduplicated until its
run is pruned. Deleted definitions retain history; live enabled **and paused**
schedules block deletion of their saved search. Delete those schedules first.

## Upgrade, backup, and rollback

1. Stop web and worker, including supervisor restart policies.
2. Back up the configured SQLite database and keep the matching old application
   revision. With both processes stopped, copy the database to a separate file.
3. Rehearse on a disposable database copy using isolated database, locks and logs.
   Start only that copy; migration 5 is additive and preserves versions 1–4 data.
4. Upgrade dependencies/code, start the web application, create a paused test
   schedule, then start the worker and verify health before enabling real work.
5. To disable scheduling, stop the worker and pause schedules. Manual job fetching
   remains usable with the upgraded schema.

For rollback, stop both processes and restore **both** the matching old code and
its pre-upgrade database. Older migration runners reject unknown migration 5;
simply pointing old code at the upgraded database is not a rollback. Restoration
loses changes made after the backup. Prefer a forward fix when retaining new data
matters. Do not edit `schema_migrations` manually or drop scheduler tables in place.
