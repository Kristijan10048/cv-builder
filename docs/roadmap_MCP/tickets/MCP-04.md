# MCP-04: Implement the CV Builder API client

**Status:** Pending.
**Summary:** Add a typed, read-only HTTP adapter for CV Builder's existing GET endpoints.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Define BaseApplyKitClient and HttpApplyKitClient with explicit methods for
   overview, application listing, application detail, and stored-job listing.
   Inject the HTTP transport so unit tests use mocked responses.
2. Restrict requests to the four mapped GET routes. Encode filters as query
   parameters, validate application identifiers, disable redirects/environment
   proxies, apply the configured timeout, and close the client on shutdown.
3. Define typed response models and explicitly select allowed output fields.
   Do not forward arbitrary response dictionaries or upstream response bodies
   in errors. Required missing fields and malformed JSON become schema errors;
   unknown extra fields are omitted.
4. Paginate the filtered application array inside the adapter using the roadmap's
   envelope and clamping rules. Preserve API item order. Forward stored-job
   pagination unchanged; do not invent a job-detail endpoint.
5. Define distinct adapter errors for not found, upstream validation failure,
   connection failure, timeout, invalid response, and other HTTP errors.

**Deliverable:** Client abstraction, HTTP implementation, response models, and
mock-transport unit tests for the four endpoints and error categories.

**Done when:** Tests verify query encoding, field projection, empty results,
application page boundaries, upstream error mapping, and resource cleanup.
Every outbound method is GET on an allowed route; no production import of
app.main, direct SQLite access, SQL, migrations, scraping, or LM Studio is used.
Note that upstream application retrieval remains unpaginated.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-04-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/src/applykit_mcp/client.py`
- `mcp_server/src/applykit_mcp/models.py`
- `mcp_server/src/applykit_mcp/errors.py`
- `mcp_server/tests/test_api_client.py`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest .\mcp_server\tests\test_api_client.py
~~~

Use mocked HTTP transport. Cover all four routes and each error category, verify parameters and field projection, and use deterministic pagination examples.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-01](MCP-01.md), [MCP-03](MCP-03.md). **Estimate:** 3 hours.
