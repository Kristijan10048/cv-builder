# Jira coding agent

This folder contains the Jira scheduler, PowerShell launcher, dependencies, and
offline regression tests. The scheduler reads tickets and asks the local Codex
CLI to implement them in a Git checkout. Changes remain in the local working
tree; the worker does not commit, push, create pull requests, or update Jira.

## Start

Run these commands from the CV Builder project root using its existing virtual
environment. The Codex CLI must be available and signed in as the user running
the scheduler.

```powershell
.\.venv\Scripts\python.exe -m pip install -r coding_agent/jira_agent/requirements.txt

$env:JIRA_URL = 'https://your-company.atlassian.net'
$env:JIRA_EMAIL = 'your-email@example.com'
$env:JIRA_API_TOKEN = 'your-api-token'
$env:JIRA_PROJECT = 'YOUR_PROJECT_KEY'
$env:JIRA_STATUS = 'Waiting for AI Developer'

.\.venv\Scripts\python.exe -m coding_agent.jira_agent
```

Replace the example values with your Jira configuration. For dev/testing, you
can instead copy [`.env.example`](.env.example) to `.env` in this folder and fill
in your values. Both entry points automatically use this file for settings absent
from the process environment. The file is found relative to `jira_agent.py`,
regardless of the working directory. `.env` is ignored by Git.

The direct script entry point also works from any working directory when its
path and the Python executable path are supplied correctly:

```powershell
.\.venv\Scripts\python.exe .\coding_agent\jira_agent\jira_agent.py
```

The scheduler starts a batch of up to five tickets immediately, then repeats
every ten minutes while it remains running. Tickets run sequentially. Press
Ctrl+C to stop scheduling; shutdown waits for active work to finish its CSV
update. Windows Task Scheduler is not required.

## Configuration

Required environment variables are `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
and `JIRA_PROJECT`.

See [`.env.example`](.env.example) for all supported configuration variables,
with placeholders and optional defaults. Process settings take precedence over
`.env` values, followed by the defaults below. A missing `.env` file is fine;
required settings are still validated. File values are used for configuration
without being added to the process environment.

| Optional setting | Default and behavior |
| --- | --- |
| `JIRA_STATUS` | `Waiting for AI Developer`; use the workflow status on the tickets in your chosen board column. |
| `POLL_INTERVAL` | `600`; positive interval in seconds. |
| `JIRA_AGENT_REPOSITORY` | The CV Builder project root, two directories above this folder; set an explicit path to edit another existing Git checkout. |
| `JIRA_AGENT_CSV_PATH` | `jira_agent_tickets.csv`, resolved relative to the target repository; absolute paths are also supported. |
| `AGENT_CMD` | `codex --ask-for-approval never exec --sandbox workspace-write {prompt}`; any replacement must contain `{prompt}`. |
| `AGENT_TIMEOUT` | `1800`; positive per-ticket timeout in seconds. |

The previous `agent-ready` label is not required. Completed CSV keys are excluded
from the Jira query before applying the five-ticket batch limit.

## History and concurrency

Generated `jira_agent_tickets.csv` and `.jira_agent.lock` remain in the target
repository root. Keeping these paths preserves existing history and coordinates
workers editing the same checkout, even when they use different script paths.
The CSV path can be configured separately; the lock always belongs to the target
repository. Use a separate CSV per project and retain it across restarts.

The CSV has `implemented_ticket` and `currently_implementing_ticket` columns,
with a separate row for each ticket. Current work is cleared after success or
failure, or on the next batch after an interruption. Completed history survives
restarts. CSV history is reloaded under the repository lock before every batch.

APScheduler permits one active batch and coalesces missed runs. The repository
lock prevents multiple worker processes from implementing tickets concurrently.
Errors are printed and retried on a later interval. Failed tickets remain
eligible, and any partial changes remain locally for inspection.

A ticket is recorded as complete only when the coding CLI succeeds, produces
new Git-visible changes, and ends its response with
`JIRA_AGENT_IMPLEMENTED:<ticket-key>`. The prompt instructs the coding agent to
run appropriate tests. The scheduler checks that confirmation rather than
independently rerunning the project's tests.

## PowerShell launcher

```powershell
.\coding_agent\jira_agent\Run-JiraAgent.ps1
```

The launcher uses the project root's `.venv` and fills unset process settings
from persistent user settings. Settings entered in the current terminal take
precedence, followed by the local `.env` fallback. Python reports missing required
Jira settings after loading that fallback.
Full output, including Python tracebacks, appears in the console and is appended
to `logs/jira-agent.log` inside this folder. The launcher's exit code matches
Python's exit code.

An optional `-CodexExecutable` argument supplies an explicit CLI path when
`AGENT_CMD` is unset. Use `-PythonExecutable` to select a different Python
executable. Existing shortcuts or Windows tasks pointing to the former
root-level launcher need their paths updated.

## Tests

Run offline worker tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s coding_agent/jira_agent/tests -v
```

These tests use temporary files and mocked Jira/CLI collaborators. The project's
`requirements-dev.txt` includes the worker dependencies so a full
`.\.venv\Scripts\python.exe -m pytest` run also discovers these tests.
