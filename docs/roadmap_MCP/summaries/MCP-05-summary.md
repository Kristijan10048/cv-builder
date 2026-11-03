# MCP-05: Assemble the stdio MCP server

Launch an independent stdio MCP process and manage the injected API client's lifecycle.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/src/cv_builder_mcp/server.py`; `mcp_server/src/cv_builder_mcp/__main__.py`; `mcp_server/tests/test_server_lifecycle.py`.

**Verify:** Verify startup without CV Builder, handshake, EOF/shutdown cleanup, and failed startup cleanup. Do not install a Windows service or add an MCP HTTP listener.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-04](../tickets/MCP-04.md). **Estimate:** 2 hours of human development effort.

[Full ticket](../tickets/MCP-05.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
