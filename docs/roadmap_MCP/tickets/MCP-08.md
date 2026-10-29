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

**Depends on:** [MCP-07](MCP-07.md). **Estimate:** 3 hours.
