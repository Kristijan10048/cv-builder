# MCP-08: Verify protocol and CV Builder integration

**Status:** Pending.
**Summary:** Prove that all tools match CV Builder data, survive failures, and preserve stored records.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Build disposable application fixtures with applications in several statuses,
   searchable text, stored jobs, saved preferences, nullable fields, and linked
   applied flags. Redirect all database and log paths before application startup;
   let normal migrations initialize only the temporary database.
2. Exercise the adapter against the real FastAPI application through an injected
   test transport. Compare projected MCP outputs with API results for the same
   filters and pages, including the adapter's application pagination.
3. Add an SDK stdio subprocess test that starts the MCP server and a disposable
   loopback CV Builder instance. Verify initialization, discovery, schemas, and
   successful calls to all four tools.
4. Cover wrong/missing/extra arguments, not found, upstream validation failures,
   timeout, connection failure, malformed JSON/schema, and HTTP server errors.
   Use mocked HTTP for deterministic failure cases; verify a later call succeeds.
5. Snapshot business-table contents after fixture setup and before tool calls.
   Compare them afterward, including applications, jobs, templates, settings,
   preferences, and profiles. Record request methods to verify no write route
   was called. Do not require database-file byte equality because app lifecycle
   and logging may have legitimate side effects.
6. Bound waits and guarantee cleanup of subprocesses, ports, temporary paths,
   and clients, even after assertion failures.

**Deliverable:** Repeatable unit, real-API integration, and stdio transport tests
plus a record of the commands and tested versions.

**Done when:** Tests pass without real job-board requests, LM Studio, or the
user's data; all four outputs agree with API semantics; logs omit payloads;
business records remain unchanged; subprocesses terminate cleanly.
Run existing application regression checks if shared application code changes.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-08-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/tests/conftest.py`
- `mcp_server/tests/helpers/disposable_application.py`
- `mcp_server/tests/integration/test_api_equivalence.py`
- `mcp_server/tests/integration/test_stdio_workflow.py`
- `mcp_server/tests/integration/test_data_preservation.py`
- `mcp_server/docs/verification.md`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv-integration\Scripts\python.exe -m pytest .\mcp_server\tests
~~~

Create the integration environment as described in the guide. Isolate DATA_DIR, DB_PATH, and log paths in each application process. Check profiles through the settings table, use bounded process waits, and record the complete suite's results.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-07](MCP-07.md). **Estimate:** 3 hours.
