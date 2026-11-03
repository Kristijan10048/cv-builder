# MCP-06: Expose application history tools

Expose filtered application history and one application's allowed detail fields.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/src/cv_builder_mcp/tools/__init__.py`; `mcp_server/src/cv_builder_mcp/tools/applications.py`; `mcp_server/src/cv_builder_mcp/server.py`; `mcp_server/tests/test_application_tools.py`.

**Verify:** Test with an SDK client and an injected fake BaseCvBuilderClient. Assert strict argument validation, output schemas, field omissions, pagination, and recovery after errors.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-05](../tickets/MCP-05.md). **Estimate:** 3 hours of human development effort.

[Full ticket](../tickets/MCP-06.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
