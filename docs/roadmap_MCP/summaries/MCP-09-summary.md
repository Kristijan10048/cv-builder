# MCP-09: Automate Inspector verification

Use the Inspector CLI to check discovery, all four tools, and expected failures without desktop interaction.

**Owner:** Coding agent. **Status:** Pending.

**Result:** `mcp_server/scripts/Verify-Inspector.ps1`; `mcp_server/tools/package.json`; `mcp_server/tools/package-lock.json`; `mcp_server/docs/stdio-launch.example.json`; `mcp_server/docs/verification.md`.

**Verify:** Run the guide's pinned npm installation first. Use the disposable application helper, check actual result JSON and exit codes, and distinguish separate CLI invocations from same-session SDK checks.
Run the focused command in the full ticket.

**Prerequisites:** [MCP-08](../tickets/MCP-08.md). **Estimate:** 1 hour of human development effort.

[Full ticket](../tickets/MCP-09.md) | [Execution guide](../coding_agent_execution.md) | [Roadmap](../mcp_server_roadmap.md)
