# MCP-03: Add local API configuration and logging

Validate local API settings and send content-free diagnostics to stderr.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/src/cv_builder_mcp/constants.py`; `mcp_server/src/cv_builder_mcp/configuration.py`; `mcp_server/src/cv_builder_mcp/diagnostic_logging.py`; `mcp_server/tests/test_configuration.py`; `mcp_server/tests/test_diagnostic_logging.py`.

**Verify:** Use table-driven cases for valid/invalid URLs and timeouts. Assert stderr output and empty stdout; avoid any actual API connection while loading settings.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-02](../tickets/MCP-02.md). **Estimate:** 2 hours of human development effort.

[Full ticket](../tickets/MCP-03.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
