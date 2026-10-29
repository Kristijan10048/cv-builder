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

**Depends on:** [MCP-06](MCP-06.md). **Estimate:** 2 hours.
