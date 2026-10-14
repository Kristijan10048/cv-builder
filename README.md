# ApplyKit

ApplyKit is a local, private workspace for building and tracking tailored job
applications. It uses FastAPI and SQLite, stores reusable source documents, and
can ask a locally running LM Studio model to tailor a CV or cover letter.

## Run

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Scheduled Jira implementation

Starting `jira_agent.py` starts an [APScheduler](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
interval scheduler. It fetches one batch of up to five Jira tickets immediately,
then every **10 minutes** while the script remains running. By default it selects
the workflow status **Waiting for AI Developer**. Each ticket is implemented
locally with the Codex CLI and recorded in `jira_agent_tickets.csv`. The worker
reads Jira without changing its labels or posting comments, and changes remain
in the local working tree.

Install dependencies and sign in to the Codex CLI as the user running the script.
Configure `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_PROJECT` as
environment variables in that process. Windows Task Scheduler is no longer needed.

Optional settings:

- `POLL_INTERVAL`: positive interval in seconds (default 600, or 10 minutes).
- `JIRA_STATUS`: workflow status to pull from (default `Waiting for AI Developer`).
- `JIRA_AGENT_REPOSITORY`: existing Git checkout to edit (defaults to this script's directory).
- `JIRA_AGENT_CSV_PATH`: CSV path, resolved relative to the implementation repository.
- `AGENT_CMD`: another coding CLI template containing `{prompt}`.
- `AGENT_TIMEOUT`: positive per-ticket timeout in seconds (default 1800).

Jira board columns map to workflow statuses. Set `JIRA_STATUS` to the status name
on the tickets in your chosen column. The previous `agent-ready` label is not
required. Completed CSV keys are excluded from the Jira query before the batch
limit is applied.

The default command uses `codex --ask-for-approval never exec --sandbox workspace-write`,
following [OpenAI's non-interactive CLI documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
The prompt asks the agent to validate its work and return
`JIRA_AGENT_IMPLEMENTED:<ticket-key>` as its final line. A ticket is completed
only when the command succeeds, that confirmation is present, and new Git-visible
changes exist. This checks the agent's confirmation; it does not independently
rerun the project's tests. Failed tickets remain eligible for a later batch,
and any partial changes remain locally for inspection.

Start the scheduler:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:POLL_INTERVAL = '600'
$env:JIRA_STATUS = 'Waiting for AI Developer'
.\.venv\Scripts\python.exe .\jira_agent.py
```

APScheduler allows only one active batch and coalesces missed runs. A repository
lock also prevents two script instances from implementing tickets concurrently.
CSV history is reloaded under that lock for every batch. Errors are printed to
the console and retried on a later interval. Press Ctrl+C to stop scheduling;
shutdown waits for an active implementation to finish updating its CSV. The
script must stay running for subsequent batches to execute.

The CSV retains two columns: `implemented_ticket` for completed keys and
`currently_implementing_ticket` for the active key. Each ticket occupies its own
row. Current work is cleared after success or failure and at the next startup
after an interrupted run. Completed history survives restarts and prevents
duplicate implementations. Use a separate CSV per project.

## Endpoint logging

Python's standard logging records every HTTP request, including API routers,
pages, static files, validation failures, and errors. Logs go to
`logs/applykit.log` by default. Files rotate at 5 MB, keeping three backups.
Application logs (including job searches and failures) use the same file.

Set `APPLYKIT_LOG_DIR` to change the directory (relative paths are resolved from
the project directory), and `APPLYKIT_LOG_LEVEL` to select verbosity:

- `INFO`: method, route template, HTTP status, elapsed milliseconds, job-search
  parameters, board counts, and search completion summaries.
- `DEBUG`: also records request start events.
- `TRACE` (default): also records individual job-search results with complete
  source data, ASGI message types, body byte counts, and streaming flags.

Request/response bodies, query strings, headers, and dynamic path values are
not included in request logs. Unhandled failures record the exception type and
are re-raised for the normal server error handling.

```powershell
$env:APPLYKIT_LOG_DIR = 'C:\ApplyKitLogs'
$env:APPLYKIT_LOG_LEVEL = 'TRACE'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## LM Studio

Start LM Studio's local server and load a model. In ApplyKit, open **Settings**,
keep the default URL (`http://localhost:1234/v1`) or enter your server URL, then
use **Test connection**. Save an application before generating its tailored
documents.

## Included

- `.tex` upload and storage for the base CV and cover letter
- Job description, status, notes, and tailored document storage
- Personal details stored locally for browser autofill
- Firefox autofill extension mockup in `firefox-extension/`
- Searchable application history
- Local SQLite database at `data/cv_builder.db`
- Versioned SQLite migrations applied automatically at startup
- Public job-page import with stored HTML
- Indeed `window._initialData` extraction when present
- LM Studio's OpenAI-compatible chat completions endpoint
- Up to 10 saved job searches with title, country, city, radius, description keywords, and posting age

## Firefox autofill mockup

Save your profile under **Settings → Personal details**, then follow the setup
steps in [`firefox-extension/README.md`](firefox-extension/README.md). The
extension fills only empty fields and never submits a form.

## Database migrations

Schema updates are versioned in `app/db_migrations/` and recorded in the
database's `schema_migrations` table. See
[`app/db_migrations/README.md`](app/db_migrations/README.md) before making a
schema change.

Open **Job Search Preferences** in the sidebar to add, edit, or delete saved
searches. Country, city, description keywords, and posting age are optional.
The city radius is in kilometres (0–1000); a radius above zero needs a city.
These preferences are stored locally and used by **Available Jobs** searches.

Country and City use dropdowns. Select a country to load its city choices;
changing the country clears the city and radius. **Other city** lets you enter
a place outside the list, including a city without a country. Existing saved
locations remain selectable when editing. Choices come from the bundled
[GeoNames catalog](https://github.com/yaph/geonamescache) (cities with populations
of at least 15,000) and work offline. A failed catalog load offers **Retry locations**.

## Job search

Open **Available Jobs**, choose a saved search and job boards, then select
**Fetch jobs**. [JobSpy](https://github.com/speedyapply/JobSpy) searches the selected boards concurrently; postings and
their complete source data are saved locally. Repeat searches update existing
postings instead of adding duplicates. Previously fetched jobs remain available
after empty searches or board failures.

LinkedIn, Indeed, Glassdoor, and ZipRecruiter are selected by default. Bayt,
BDJobs, and Naukri are also available. Indeed and Glassdoor require a supported
country; ZipRecruiter covers US/Canada, BDJobs Bangladesh, and Naukri India.
Unsupported boards and failed requests show warnings while successful board
results are retained. JobSpy may return empty results when a board blocks it.
Glassdoor HTTP 429 responses show a rate-limit warning and pause new Glassdoor
searches for five minutes in the current app process. Other boards continue,
and jobs received before the limit are kept with a partial status. This cooldown
does not guarantee that Glassdoor will allow requests when it ends.

Saved search titles, locations, radii (converted from kilometres to miles), and
posting ages are passed to JobSpy. All saved description keywords must match
the fetched description, ignoring case. Availability and location/date filter
precision depend on each board. Fetching can take several minutes.

Filter stored jobs by saved search, board, or text. Previous/Next and the page
size control browse the database without fetching again. Applied status reflects
saved applications with the same job URL in Applied, Interview, or Offer status.

Available Jobs appears directly below Overview and uses the workspace width,
including when the sidebar is collapsed. Its **Language** column lists explicit
spoken-language requirements detected in each stored description. The initial
regex parser recognizes common English, German, and Dutch requirement phrases,
including proficiency and CEFR levels, and ignores incidental, optional, or
negated mentions. Language names are normalized; the column does not display
proficiency levels or distinguish alternative languages from joint requirements.
**Not specified** means no explicit requirement was detected, rather than proof
that none exists. Unusual wording can be missed. Existing jobs are parsed when
listed, so no refetch or database migration is needed. The parser has a replaceable
interface for a future local LLM integration.

- `POST /api/job-search`: `{ "preference_id": 1, "sites": ["indeed", "linkedin"], "results_wanted": 50 }`
- `GET /api/available-jobs?page=1&page_size=20`: paginated results and totals;
  optional `preference_id`, `site`, and `search` filters.

The requested result limit is 1–1000 per board, with a default of 50. The UI offers
20, 50, 100, 250, 500, and 1,000. For a daily search, save **Dates posted → Last 24
hours** in Job Search Preferences, then choose **1,000** in Available Jobs. This
passes `hours_old=24` and `results_wanted=1000` to JobSpy without changing other
saved criteria. Description keywords filter that source batch afterward.

Larger requests can take longer and do not prove full coverage. The installed
JobSpy 1.2.0 Glassdoor scraper clamps requests to 900 postings; its LinkedIn
scraper stops at a source start offset of 1000. Board blocking, inaccessible
details, filter precision, and additional postings beyond the requested limit can
still leave matches unfetched. Stored result pages continue to support 1–100 jobs.
Migration 4 adds `available_jobs` and `job_search_results` and preserves existing
applications, settings, documents, and search preferences.

The [PLLKTTSTS-15 completeness plan](docs/PLLKTTSTS-15-job-fetch-completeness-plan.md)
describes how to verify coverage across boards, current retrieval limitations,
proposed implementation steps, and an effort estimate. It prioritizes the EU
(especially Germany and the Netherlands) and Switzerland, then the USA, excludes
Asia, and defines configurable region expansion. The separate
[verification test plan](docs/PLLKTTSTS-15-job-fetch-verification-tests.md) specifies
offline fixtures and independent live comparisons. These are planning documents;
coverage verification is not yet implemented.

Short versions with examples: [plan summary](docs/PLLKTTSTS-15-job-fetch-completeness-plan-summary.md)
and [test summary](docs/PLLKTTSTS-15-job-fetch-verification-tests-summary.md).

Run the automated checks with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Tests use temporary databases and preserve your saved applications and settings.
