# MCP-04: Implement the CV Builder API client

Implement the typed GET-only adapter, field selection, pagination, and upstream error mapping.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/src/applykit_mcp/client.py`; `mcp_server/src/applykit_mcp/models.py`; `mcp_server/src/applykit_mcp/errors.py`; `mcp_server/tests/test_api_client.py`.

**Verify:** Use mocked HTTP transport. Cover all four routes and each error category, verify parameters and field projection, and use deterministic pagination examples.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-01](../tickets/MCP-01.md), [MCP-03](../tickets/MCP-03.md). **Estimate:** 3 hours of human development effort.

[Full ticket](../tickets/MCP-04.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
