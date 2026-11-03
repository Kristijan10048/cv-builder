# MCP-07: Expose overview and stored-job tools

**Status:** Pending.
**Summary:** Show CV Builder application statistics and browse jobs already stored by the application.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Register get_overview without arguments. Return total, by_status, and the
   allowlisted recent-application summaries from GET /api/overview.
2. Register list_available_jobs with page, page_size, preference_id, site, and
   search. Match the existing API's defaults, bounds, and supported board values.
3. Preserve the stored-job page envelope, applied flags, language requirements,
   nullable fields, ordering, and API page clamping. Return only the listing
   fields specified in the roadmap; descriptions are not available on this route.
4. State in tool descriptions that results are saved data. Never invoke
   POST /api/job-search, an importer, external boards, or document generation.

**Deliverable:** Two more registered tools with typed schemas and client tests.

**Done when:** A client discovers exactly the four planned tools. Tests verify
overview counts/recent items, empty and populated job pages, filters, invalid
boards, unknown preferences, invalid pagination, page clamping, and nullable job
fields. Results match the API and successful calls still work after errors.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-07-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/src/cv_builder_mcp/tools/overview.py`
- `mcp_server/src/cv_builder_mcp/tools/available_jobs.py`
- `mcp_server/src/cv_builder_mcp/server.py`
- `mcp_server/tests/test_overview_job_tools.py`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest .\mcp_server\tests\test_overview_job_tools.py
~~~

Verify discovery returns exactly four tools, preserve nullable fields/applied flags, and assert neither tool triggers a scraper, importer, generator, or write route.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-06](MCP-06.md). **Estimate:** 2 hours.
