# MCP-09: Connect Inspector and a local host

**Status:** Pending.
**Summary:** Verify that real MCP clients can use the CV Builder tools through stdio.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Start a disposable CV Builder instance from the integration-test fixtures
   on a loopback port and point APPLYKIT_MCP_API_URL at that instance.
2. Check the chosen MCP Inspector version's runtime requirements and launch
   the installed MCP package through its absolute Python interpreter path.
3. Discover the four tools, inspect their schemas, and call each with representative
   filters/identifiers. Also call an unknown application and confirm recovery.
4. Select one available local MCP host and prepare its exact launch configuration.
   Include absolute interpreter, module arguments, package installation assumption,
   environment values, and working directory if that host supports one.
5. Verify the same discovery and calls in the selected host. Record exact client
   versions and observed results; label any other examples as untested.

**Deliverable:** Inspector/host smoke-test record and a working local-host config
example using synthetic data.

**Done when:** Both clients discover all four tools and display successful results.
Invalid calls leave the session usable. Stopping the disposable CV Builder instance
produces a clear unavailable-app error; restarting it allows subsequent calls.

**Depends on:** [MCP-08](MCP-08.md). **Estimate:** 1 hour.
