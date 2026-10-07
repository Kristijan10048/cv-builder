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

## Endpoint logging

Python's standard logging records every HTTP request, including API routers,
pages, static files, validation failures, and errors. Logs go to
`logs/applykit.log` by default. Files rotate at 5 MB, keeping three backups.
Application logs (including job-search failures) use the same file.

Set `APPLYKIT_LOG_DIR` to change the directory (relative paths are resolved from
the project directory), and `APPLYKIT_LOG_LEVEL` to select verbosity:

- `INFO` (default): method, route template, HTTP status, and elapsed milliseconds.
- `DEBUG`: also records request start events.
- `TRACE`: also records ASGI message types, body byte counts, and streaming flags.

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

Saved search titles, locations, radii (converted from kilometres to miles), and
posting ages are passed to JobSpy. All saved description keywords must match
the fetched description, ignoring case. Availability and location/date filter
precision depend on each board. Fetching can take several minutes.

Filter stored jobs by saved search, board, or text. Previous/Next and the page
size control browse the database without fetching again. Applied status reflects
saved applications with the same job URL in Applied, Interview, or Offer status.

- `POST /api/job-search`: `{ "preference_id": 1, "sites": ["indeed", "linkedin"], "results_wanted": 50 }`
- `GET /api/available-jobs?page=1&page_size=20`: paginated results and totals;
  optional `preference_id`, `site`, and `search` filters.

The result limit is 1–100 per board. Stored result pages support 1–100 jobs.
Migration 4 adds `available_jobs` and `job_search_results` and preserves existing
applications, settings, documents, and search preferences.

Run the automated checks with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Tests use temporary databases and preserve your saved applications and settings.
