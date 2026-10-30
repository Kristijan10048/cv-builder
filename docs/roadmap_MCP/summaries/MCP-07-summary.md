# MCP-07: Expose overview and stored-job tools

Expose application statistics and stored-job listings with the API's filters and pagination.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/src/applykit_mcp/tools/overview.py`; `mcp_server/src/applykit_mcp/tools/available_jobs.py`; `mcp_server/src/applykit_mcp/server.py`; `mcp_server/tests/test_overview_job_tools.py`.

**Verify:** Verify discovery returns exactly four tools, preserve nullable fields/applied flags, and assert neither tool triggers a scraper, importer, generator, or write route.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-06](../tickets/MCP-06.md). **Estimate:** 2 hours of human development effort.

[Full ticket](../tickets/MCP-07.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
