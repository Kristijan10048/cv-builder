# MCP-08: Verify protocol and CV Builder integration

Validate all tools against disposable CV Builder data and prove business records are preserved.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/tests/conftest.py`; `mcp_server/tests/helpers/disposable_application.py`; `mcp_server/tests/integration/test_api_equivalence.py`; `mcp_server/tests/integration/test_stdio_workflow.py`; `mcp_server/tests/integration/test_data_preservation.py`; `mcp_server/docs/verification.md`.

**Verify:** Create the integration environment as described in the guide. Isolate DATA_DIR, DB_PATH, and log paths in each application process. Check profiles through the settings table, use bounded process waits, and record the complete suite's results.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-07](../tickets/MCP-07.md). **Estimate:** 3 hours of human development effort.

[Full ticket](../tickets/MCP-08.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
