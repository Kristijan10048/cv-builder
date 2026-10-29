# MCP-05: Assemble the stdio MCP server

**Status:** Pending.
**Summary:** Connect the official SDK to the CV Builder client with a clean lifecycle.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Implement ApplyKitMcpServer with injected configuration and BaseApplyKitClient.
   Keep HTTP and application-specific logic out of protocol assembly.
2. Add a server factory and a module entry point that starts the SDK's stdio
   runner only under the main guard.
3. Construct and close the HTTP client in the server lifecycle. Ensure cleanup
   on ordinary shutdown and failed initialization.
4. Keep initialization independent of CV Builder availability. An unavailable
   application should fail a tool call later, while the MCP session stays alive.

**Deliverable:** Runnable stdio server assembly and lifecycle checks; tool
registration follows in MCP-06 and MCP-07.

**Done when:** An SDK client launches the subprocess, initializes, receives the
configured server identity, and shuts down cleanly without CV Builder running.
Importing the module starts nothing. Diagnostics do not corrupt stdout, and
cleanup leaves no child process or open client behind.

**Depends on:** [MCP-04](MCP-04.md). **Estimate:** 2 hours.
