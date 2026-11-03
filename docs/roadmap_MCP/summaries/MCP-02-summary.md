# MCP-02: Create the isolated MCP package

Create the independently installable Python package, pinned development dependencies, and import checks.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/pyproject.toml`; `mcp_server/.gitignore`; `mcp_server/src/cv_builder_mcp/__init__.py`; `mcp_server/src/cv_builder_mcp/__main__.py`; `mcp_server/tests/test_imports.py`.

**Verify:** Use the guide's bootstrap commands. Assert imports do not launch a server or access the API/database. Add package-local ignore rules for both environments, caches, metadata, node_modules, and generated results.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-01](../tickets/MCP-01.md). **Estimate:** 1 hour of human development effort.

[Full ticket](../tickets/MCP-02.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
