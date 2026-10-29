# MCP-03: Add local API configuration and logging

**Status:** Pending.
**Summary:** Configure the CV Builder connection and isolate diagnostics from MCP traffic.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Implement ApplyKitMcpConfiguration with server identity, stdio transport,
   API URL, and request timeout.
2. Read APPLYKIT_MCP_API_URL (default http://127.0.0.1:8000) and
   APPLYKIT_MCP_REQUEST_TIMEOUT_SECONDS (default 10 seconds). Reject missing host,
   non-loopback host, non-HTTP scheme, credentials, query/fragment, an unexpected
   base path, and nonpositive or nonfinite timeout values. Accept localhost,
   127.0.0.1, and IPv6 loopback with an optional valid port and root slash.
3. Centralize fixed values in C_ constants, with C_APPLYKIT_ names for
   application-specific routes, environment names, and limits.
4. Configure stderr logging with method, route template, elapsed time, and
   error category. Exclude search terms, record contents, full URLs with queries,
   and document/profile payloads.

**Deliverable:** Configuration and logging classes with focused tests.

**Done when:** Defaults and environment overrides work; invalid settings fail
clearly on stderr before serving; a captured log creates no stdout output.
No API call, database connection, or migration is performed while loading config.

**Depends on:** [MCP-02](MCP-02.md). **Estimate:** 2 hours.
