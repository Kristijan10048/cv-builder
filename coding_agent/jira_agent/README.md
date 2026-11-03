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
can instead create a local `.env` file in this folder with the same variable names
and your values, using NAME=value lines (without the PowerShell prefix).
Both entry points automatically use this file for settings absent
from the process environment. The file is found relative to `jira_agent.py`,
regardless of the working directory. `.env` is ignored by Git.

The direct script entry point also works from any working directory when its
path and the Python executable path are supplied correctly:

```powershell
.\.venv\Scripts\python.exe .\coding_agent\jira_agent\jira_agent.py
```

Before scheduling, the script tests the connection and API token with a read-only
[`GET /rest/api/2/myself`](https://developer.atlassian.com/cloud/jira/platform/rest/v2/api-group-myself/#api-rest-api-2-myself-get)
request. It prints whether authentication succeeded. Invalid credentials, denied
access, timeouts, connection failures, or an unexpected response stop startup
with exit code 1, before any ticket is fetched or implemented. The request has a
30-second timeout. This confirms authentication; project and ticket permissions
are checked when the normal Jira search runs.

Startup output shows the effective `JIRA_URL`, `JIRA_EMAIL`, and `JIRA_PROJECT`
and confirms `JIRA_API_TOKEN loaded: yes (value hidden)`. A missing or blank token
fails required-setting validation; the token value is never included in the summary.

After the check succeeds, the scheduler starts a batch of up to five tickets immediately, then repeats
every ten minutes while it remains running. Tickets run sequentially. Press
Ctrl+C to stop scheduling; shutdown waits for active work to finish its CSV
update. Windows Task Scheduler is not required.

## List tickets or projects

Run these commands from the project root:

```powershell
# All visible tickets in JIRA_PROJECT, across every status.
.\.venv\Scripts\python.exe -m coding_agent.jira_agent --tickets

# Override JIRA_PROJECT for this command (project key or quoted name).
.\.venv\Scripts\python.exe -m coding_agent.jira_agent --tickets YOUR_PROJECT_KEY

# All projects visible to your Jira account; JIRA_PROJECT is not required.
.\.venv\Scripts\python.exe -m coding_agent.jira_agent --projects

# Show command help without connecting to Jira.
.\.venv\Scripts\python.exe -m coding_agent.jira_agent --help
```

Ticket output includes key, status, and summary. Project output includes key and
name. Both commands authenticate first, fetch all result pages, print a total,
and exit. They do not start the scheduler or coding agent, or create/update the
ticket CSV or worker lock. Jira permissions determine which results are visible.
Choose one listing flag per invocation. With no flag, the scheduler runs normally.
The same flags work with the direct `jira_agent.py` script.

The PowerShell launcher supports equivalent switches:

```powershell
.\coding_agent\jira_agent\Run-JiraAgent.ps1 -Tickets
.\coding_agent\jira_agent\Run-JiraAgent.ps1 -Tickets -Project YOUR_PROJECT_KEY
.\coding_agent\jira_agent\Run-JiraAgent.ps1 -Projects
```

## Configuration

Required environment variables are `JIRA_URL`, `JIRA_EMAIL`, and `JIRA_API_TOKEN`.
`JIRA_PROJECT` is also required for scheduling and for `--tickets` without an
explicit project argument. It is optional for `--projects`.

The required settings above and optional settings below describe the supported
configuration. Process settings take precedence over
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

Both Python entry points and the launcher print progress immediately. Messages
include UTC timestamps, configuration paths, repository locking, Jira search
criteria and results, ticket position, coding-agent execution and verification,
CSV updates, batch failure counts, and waiting/shutdown status. While a coding
command is active, a progress message appears every 15 seconds. These messages
show that the command is still running; detailed coding-agent output remains
captured for completion checks and error reporting. Jira API tokens are redacted.

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
