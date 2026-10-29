# CV Builder MCP server development roadmap

Status: planned. This document and its tickets define future implementation work.

## Goal and first milestone

Give a local MCP client read-only access to CV Builder (ApplyKit): review application
progress, find saved applications, inspect an application, and browse already fetched
jobs. Use the official Python MCP SDK and stdio for the client connection.

The brief specifies the application but not individual capabilities. The initial
read-only scope below is a proposed, concrete starting point. Document generation,
application changes, job fetching, and personal-profile access are later increments.

## Architecture grounded in the current application

Run a small standalone MCP process alongside the existing FastAPI application:

MCP host -> stdio -> ApplyKit MCP server -> local HTTP GET -> CV Builder API -> SQLite.

Reuse the existing HTTP API through an injected HTTP client. Do not import
`app.main` into the production MCP process, copy SQL, access SQLite directly, or
run database migrations from MCP. The existing application owns database startup.
It must be running before a tool can retrieve data; MCP initialization itself
does not require it to be available.

Proposed package location: `mcp_server/` under the CV Builder project root,
with importable code in `src/applykit_mcp/`, isolated dependency declarations,
tests, and a README. Installing it must not change the application's dependencies.

| MCP tool | Existing API | Purpose |
| --- | --- | --- |
| `get_overview` | `GET /api/overview` | Application totals, counts by status, and recent application summaries. |
| `list_applications` | `GET /api/applications` | Filter application history by search text and status. |
| `get_application` | `GET /api/applications/{application_id}` | Read one application's metadata, job description, and notes. |
| `list_available_jobs` | `GET /api/available-jobs` | Browse stored jobs with existing filters, pagination, and applied flags. |

Application routes and response shapes were inspected in
[app/main.py](../../app/main.py). Stored-job validation and serialization were
inspected in [app/job_search.py](../../app/job_search.py),
[app/job_search_repository.py](../../app/job_search_repository.py), and
[app/database_models.py](../../app/database_models.py). Input definitions also
live in [app/models.py](../../app/models.py).

## Tool contract and limits

- `get_overview` takes no arguments and returns `total`, `by_status`, and
  `recent`. Recent entries expose only identifier, company, job title, status,
  and creation/update timestamps; the current API returns up to five.
- `list_applications` accepts `search=""` (up to 250 characters),
  `status=""` (up to 50 characters), `page=1`, and `page_size=20`.
  Page must be positive; page size is 1-100. Pass search/status to the API
  unchanged to preserve its semantics. Status is an exact string, not a new enum:
  the UI offers Draft, Ready, Applied, Interview, Offer, and Closed, while the
  API also accepts other stored values.
- Application list items expose only `id`, `company`, `job_title`,
  `source_url`, `status`, `created_at`, and `updated_at`. Wrap items in
  `items`, `total`, `page`, `page_size`, `total_pages`,
  `has_previous`, and `has_next`.
- The current application-list API has no pagination. Initially fetch its filtered
  array and paginate inside the MCP adapter without changing order. Use at least
  one total page, clamp an excessive page to the last page, and return an empty
  first page for no results. This bounds tool output, not upstream retrieval;
  server-side application pagination is a future performance improvement.
- `get_application` requires a strictly positive integer `application_id`.
  Return the summary fields plus `job_description` and `notes`. Explicitly
  select fields; omit `raw_html`, `imported_data`, `adjusted_cv`, and
  `adjusted_cover_letter` from this first milestone.
- `list_available_jobs` accepts the API's `page=1`, `page_size=20`
  (1-100), optional positive `preference_id`, optional `site`, and
  `search=""` (up to 250 characters). Supported sites currently are
  linkedin, indeed, glassdoor, zip_recruiter, bayt, bdjobs, and naukri.
  Forward these query parameters and preserve the API's page envelope and order,
  including its page clamping. Unknown preferences produce a not-found error.
- Job items expose the existing list fields: `id`, `site`, `job_url`,
  `job_title`, `company`, `location`, `language_requirements`,
  `date_posted`, `job_type`, `is_remote`, `first_fetched_at`,
  `fetched_at`, and `applied`. This endpoint does not return full descriptions.
- Define typed input/output models and machine-readable schemas for all tools.
  Integer inputs must reject booleans and coerced strings. Unknown arguments fail
  validation. Lists with no matches are successful empty results.
- Map missing records/preferences, upstream validation errors, application
  unavailability, timeout, malformed upstream JSON/schema, and other HTTP failures
  to distinct, concise tool execution errors. Use SDK validation errors for malformed
  MCP arguments. No failure should terminate a healthy MCP session.

## Configuration and implementation conventions

Default API URL: `http://127.0.0.1:8000`. Configure it with
`APPLYKIT_MCP_API_URL`, and use `APPLYKIT_MCP_REQUEST_TIMEOUT_SECONDS`
with a positive default of 10 seconds. Validate configuration at startup and
limit this milestone to loopback HTTP endpoints. Allow only the four mapped GET
routes; tools cannot supply arbitrary URLs. Disable redirects and environment
proxy use in the HTTP client.

Use `ApplyKitMcpConfiguration`, `BaseApplyKitClient`,
`HttpApplyKitClient`, and `ApplyKitMcpServer` classes. Inject the client
so tests can use fixtures and mocked HTTP. Close it on shutdown. Log diagnostics
to stderr, keeping stdout for MCP traffic. Do not log personal document content,
notes, descriptions, full API payloads, or search terms.

Follow [the repository guidance](../../AGENTS.md): explicit Python, descriptive
names, PascalCase classes, docstrings for every class/function, and comments for
important logic. Put fixed values in `C_<NAME>` constants, using
`C_APPLYKIT_<NAME>` for application-specific values; logging messages may
remain inline. Use base classes where the implementation needs an interface.
No new SQL, database tables, or table models are needed for this HTTP adapter.
Future database changes must reuse the existing models and migration workflow.

The MCP tools perform no business-data writes. The running application may still
write its ordinary logs or perform its normal startup migrations. Tests must use
temporary databases and log locations, never the user's saved data.

## Small implementation tasks

Each ticket has a short summary, implementation steps, deliverables, acceptance
criteria, dependencies, and an estimate. All implementation tickets remain pending.

| Ticket | Summary | Dependencies | Estimate |
| --- | --- | --- | --- |
| [MCP-01 - Define the CV Builder tool contract](tickets/MCP-01.md) | Specify the four tools against the existing application API. | None | 2 hours |
| [MCP-02 - Create the isolated MCP package](tickets/MCP-02.md) | Set up reproducible server dependencies and a module entry point. | MCP-01 | 1 hour |
| [MCP-03 - Add local API configuration and logging](tickets/MCP-03.md) | Validate the local connection settings and keep diagnostics on stderr. | MCP-02 | 2 hours |
| [MCP-04 - Implement the CV Builder API client](tickets/MCP-04.md) | Add a typed read-only adapter for the existing GET endpoints. | MCP-01, MCP-03 | 3 hours |
| [MCP-05 - Assemble the stdio MCP server](tickets/MCP-05.md) | Wire the SDK, configuration, and client lifecycle together. | MCP-04 | 2 hours |
| [MCP-06 - Expose application history tools](tickets/MCP-06.md) | Add filtered application listing and single-application retrieval. | MCP-05 | 3 hours |
| [MCP-07 - Expose overview and stored-job tools](tickets/MCP-07.md) | Add application statistics and paginated stored-job browsing. | MCP-06 | 2 hours |
| [MCP-08 - Verify protocol and CV Builder integration](tickets/MCP-08.md) | Exercise all tools, upstream failures, and data preservation. | MCP-07 | 3 hours |
| [MCP-09 - Connect Inspector and a local host](tickets/MCP-09.md) | Verify discovery and tool use in real MCP clients. | MCP-08 | 1 hour |
| [MCP-10 - Document setup and troubleshooting](tickets/MCP-10.md) | Explain how to run CV Builder and connect the MCP server. | MCP-09 | 1 hour |

## Delivery order and completion criteria

Implement MCP-01 through MCP-10 in dependency order. Estimated total:
**20 development hours**, plus environment-specific troubleshooting. Estimates
assume the API remains as inspected; any API change should update its affected
ticket and contract before implementation.

Complete the milestone when a fresh environment can install the isolated package,
a local host discovers exactly the four tools, results match the CV Builder API,
invalid calls leave the session usable, and the documented tests demonstrate that
application records, stored jobs, templates, settings, and profiles are unchanged.

The automated test suite uses a temporary seeded application, plus SDK subprocess
tests for stdio. Inspector and host smoke tests also use that disposable instance.
Do not run tests against the user's normal database.

Possible later tickets: retrieve document templates or tailored documents; expose
saved search preferences; generate a tailored CV/cover letter through the existing
LM Studio flow; create or update applications; trigger job fetching; add server-side
application pagination; or offer authenticated Streamable HTTP. Side effects and
access to personal-profile data need explicit contracts in those later increments.

## Technical references

Application inspection and reference check: 2026-10-29.

- [Official Python SDK](https://py.sdk.modelcontextprotocol.io/): choose and pin
  a compatible SDK/Python version in MCP-02; use its matching typed-tool APIs.
- [Server transports](https://py.sdk.modelcontextprotocol.io/run/): stdio supports
  a local process launched by a host; HTTP transport can be a separate increment.
- [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector): verify
  discovery, schemas, successful calls, and errors; check runtime requirements
  for the selected version during MCP-09.
