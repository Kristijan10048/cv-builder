# MCP-02: Create the isolated MCP package

**Status:** Pending.
**Summary:** Set up a reproducible Python package without changing CV Builder's dependencies.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Create the proposed mcp_server/ project folder with src/applykit_mcp/,
   package metadata, tests/, and a README placeholder.
2. Select the official Python MCP SDK and a compatible Python version. Pin the
   tested SDK, HTTP client, schema-modeling, and development dependencies, recording
   the exact environment used. Check compatibility with the SDK's matching docs.
3. Add a module entry point for python -m applykit_mcp, with a main guard and
   no network, database, or server-start side effects during imports.
4. Configure focused tests with no dependency on real job boards or LM Studio.

**Deliverable:** Installable package scaffolding and isolated runtime/development
dependency declarations. The server behavior is added in later tickets.

**Done when:** A fresh environment installs the package, imports it without
starting a process or touching the application database, and collects tests.
The CV Builder requirements files remain unchanged.

**Depends on:** [MCP-01](MCP-01.md). **Estimate:** 1 hour.
