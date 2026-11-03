# Coding-agent execution guide

This guide prepares future implementation of the CV Builder MCP server. The
roadmap is the shared contract; each full ticket is one implementation assignment.
No server, service, scheduler, or external ticket is created by these planning files.

## Start here

1. Run the coding agent with the CV Builder project root as its writable workspace.
   This planning folder is docs/roadmap_MCP/; implementation files belong in
   mcp_server/ at the project root. A workspace limited to the planning folder
   cannot perform the implementation without an appropriate workspace change.
2. Read the applicable AGENTS.md files, [the roadmap](mcp_server_roadmap.md), and
   the assigned full ticket. Read its [short summary](summaries/README.md) for
   orientation, and verify prerequisite deliverables exist and their checks pass.
3. Inspect git status and preserve unrelated changes. Inspect the current API before
   relying on the snapshot described in the roadmap. Use the pinned SDK's matching
   documentation when implementing SDK-specific behavior.
4. Implement only the assigned ticket and its focused checks. Complete its
   acceptance criteria before moving to the next ticket. If the task exceeds the
   available run time, preserve work and report remaining criteria accurately.

## Separate application and lifecycle

Implement an independently installable cv_builder_mcp application in mcp_server/.
For this milestone, an MCP host launches it over stdio and closes it with the
session. Run CV Builder separately on loopback HTTP. Do not register an operating
system service or add MCP routes to the existing FastAPI application.

Keep production MCP code independent of app.main and SQLite. Only integration
test helpers may import the application to start a disposable test instance.
The runtime environment needs MCP dependencies, not job-board scrapers or LM Studio.

## Planned layout and ownership

Paths in tickets are relative to the CV Builder project root. These are planned
outputs, not claims that files already exist.

| Owner | Main planned outputs |
| --- | --- |
| MCP-01 | mcp_server/docs/tool_contract.md; mcp_server/docs/contract_examples.json |
| MCP-02 | mcp_server/pyproject.toml; mcp_server/.gitignore; src/cv_builder_mcp/__init__.py and __main__.py; tests/test_imports.py |
| MCP-03 | src/cv_builder_mcp/constants.py, configuration.py, diagnostic_logging.py; configuration/logging tests |
| MCP-04 | src/cv_builder_mcp/client.py, models.py, errors.py; tests/test_api_client.py |
| MCP-05 | src/cv_builder_mcp/server.py; __main__.py wiring; tests/test_server_lifecycle.py |
| MCP-06 | src/cv_builder_mcp/tools/__init__.py and applications.py; tests/test_application_tools.py |
| MCP-07 | src/cv_builder_mcp/tools/overview.py and available_jobs.py; tests/test_overview_job_tools.py |
| MCP-08 | tests/conftest.py; tests/integration/; tests/helpers/disposable_application.py; integration dependency instructions |
| MCP-09 | scripts/Verify-Inspector.ps1; tools/package.json and package-lock.json; docs/stdio-launch.example.json |
| MCP-10 | mcp_server/README.md; mcp_server/docs/verification.md |

All abbreviated src/, tests/, scripts/, tools/, and docs/ entries in this table
are inside mcp_server/. Keep shared helpers small. Reuse models/constants from
earlier tickets rather than copying them into handlers.

## Bootstrap and focused validation

All commands below run in PowerShell from the CV Builder root. They are future
implementation checks and were not run while preparing this roadmap.

MCP-01 creates a contract and JSON examples; validate the JSON and compare the
document with the mapped API routes. No runtime test is needed for that ticket.

During MCP-02, select a compatible installed Python and create an isolated
environment. The developer may substitute that interpreter for python:

~~~powershell
python -m venv .\mcp_server\.venv
.\mcp_server\.venv\Scripts\python.exe -m pip install -e '.\mcp_server[dev]'
.\mcp_server\.venv\Scripts\python.exe -m pip check
.\mcp_server\.venv\Scripts\python.exe -m pytest .\mcp_server\tests\test_imports.py
~~~

Define the dev extra with the test runner and required test dependencies in
MCP-02. Pin tested direct dependencies and document the Python version. Add
package-local ignore entries for environments, caches, build metadata,
node_modules, and generated test results before creating those artifacts.

Each ticket names a focused validation command. Rerun prior affected checks when
shared code changes. At MCP-08, run the complete isolated unit suite and integration
suite. Tests must be independent of test order and external accounts.

## Disposable application integration

MCP-08 creates a separate integration environment because importing the real
FastAPI application requires its dependencies:

~~~powershell
python -m venv .\mcp_server\.venv-integration
.\mcp_server\.venv-integration\Scripts\python.exe -m pip install -r .\requirements.txt -e '.\mcp_server[dev]'
.\mcp_server\.venv-integration\Scripts\python.exe -m pip check
.\mcp_server\.venv-integration\Scripts\python.exe -m pytest .\mcp_server\tests\integration
~~~

If dependency constraints conflict, resolve and document them inside the MCP
test setup; do not silently upgrade the application requirements.

The existing root tests/conftest.py applies only to tests under that directory.
It does not protect mcp_server/tests/. Create explicit fixture isolation there.
app/database.py currently has no database-path environment override: setting
CV_BUILDER_MCP_API_URL does not isolate data.

The test helper must set app.database.DATA_DIR and DB_PATH to a temporary directory
and CV_BUILDER_LOG_DIR to a temporary log directory before importing app.main or
entering application startup. Do this inside every application subprocess as
well as in-process tests. Only then initialize migrations and synthetic fixtures.
The personal-details profile currently lives in the settings table under the
personal_details key; it is not a separate profiles table.

Have the helper accept a temporary fixture directory and selected loopback port;
the parent creates the directory, waits with a bounded deadline, and cleans up
only the processes and temporary paths it owns. Do not launch app.main:app against
the default database as an integration shortcut. On Windows, start background
GUI-capable helpers with hidden windows. No live application, board, or model is
needed to validate the contract.

## Inspector verification without desktop interaction

MCP-09 pins the Inspector package in mcp_server/tools/package.json and commits its
lock file. Check the selected package's Node runtime requirement. Use its local CLI
from the smoke script, with absolute interpreter paths and the module arguments.

~~~powershell
npm ci --prefix .\mcp_server\tools
.\mcp_server\scripts\Verify-Inspector.ps1 -McpPythonPath (Resolve-Path .\mcp_server\.venv\Scripts\python.exe).Path -ApplicationPythonPath (Resolve-Path .\mcp_server\.venv-integration\Scripts\python.exe).Path
~~~

The script owns its disposable API fixture and checks discovery, all four calls,
expected failures, and successful calls after restart. It exits nonzero on
unexpected results and records versions and result JSON. A missing Node runtime,
package installation failure, or unavailable required dependency is an actual
verification limitation; preserve that evidence and do not report a pass.

Use Inspector's CLI as the required external client. A separate desktop host is
optional; do not invent a successful manual test or require an account login for
automatic completion. The generic launch example must be valid JSON and clearly
labeled as a template until a specific host format is verified.

## Completion and handoff

Each coding-agent response should contain:

- Assigned ticket identifier and a short description of the resulting behavior.
- Changed file paths and any material difference from the ticket's planned paths.
- Commands actually run, outcomes, and any skipped checks with a concrete reason.
- Which acceptance criteria passed and which remain incomplete.
- The next dependency-ready ticket.

Update the assigned ticket's status only after its criteria pass. If its scope,
dependencies, or estimate changes, update the roadmap row and short summary too.
Documentation-only edits do not mean runtime tickets have been implemented.
Do not report the roadmap's human estimates as measured execution time.

The repository contains an optional Jira scheduler documented in
[coding_agent/jira_agent/README.md](../../coding_agent/jira_agent/README.md).
It runs Jira tickets and does not automatically ingest these local Markdown files
or enforce this dependency graph. If that workflow is later used, copy each full
ticket's requirements or make the local file accessible in the agent prompt;
release tickets in dependency order. Scheduler-specific completion markers use
the actual Jira key and its documented rules, not the local MCP identifier.
No Jira import, scheduler launch, or external update is part of this request.
