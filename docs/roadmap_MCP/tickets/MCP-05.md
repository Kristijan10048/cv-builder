# MCP-05: Assemble the stdio MCP server

**Status:** Pending.
**Summary:** Connect the official SDK to the CV Builder client with a clean lifecycle.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Implement CvBuilderMcpServer with injected configuration and BaseCvBuilderClient.
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

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-05-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/src/cv_builder_mcp/server.py`
- `mcp_server/src/cv_builder_mcp/__main__.py`
- `mcp_server/tests/test_server_lifecycle.py`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest .\mcp_server\tests\test_server_lifecycle.py
~~~

Verify startup without CV Builder, handshake, EOF/shutdown cleanup, and failed startup cleanup. Do not install a Windows service or add an MCP HTTP listener.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-04](MCP-04.md). **Estimate:** 2 hours.
