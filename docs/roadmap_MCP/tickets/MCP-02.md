# MCP-02: Create the isolated MCP package

**Status:** Pending.
**Summary:** Set up a reproducible Python package without changing CV Builder's dependencies.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Create the proposed mcp_server/ project folder with src/cv_builder_mcp/,
   package metadata, tests/, and a README placeholder.
2. Select the official Python MCP SDK and a compatible Python version. Pin the
   tested SDK, HTTP client, schema-modeling, and development dependencies, recording
   the exact environment used. Check compatibility with the SDK's matching docs.
3. Add a module entry point for python -m cv_builder_mcp, with a main guard and
   no network, database, or server-start side effects during imports.
4. Configure focused tests with no dependency on real job boards or LM Studio.

**Deliverable:** Installable package scaffolding and isolated runtime/development
dependency declarations. The server behavior is added in later tickets.

**Done when:** A fresh environment installs the package, imports it without
starting a process or touching the application database, and collects tests.
The CV Builder requirements files remain unchanged.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-02-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/pyproject.toml`
- `mcp_server/.gitignore`
- `mcp_server/src/cv_builder_mcp/__init__.py`
- `mcp_server/src/cv_builder_mcp/__main__.py`
- `mcp_server/tests/test_imports.py`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest .\mcp_server\tests\test_imports.py
~~~

Use the guide's bootstrap commands. Assert imports do not launch a server or access the API/database. Add package-local ignore rules for both environments, caches, metadata, node_modules, and generated results.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-01](MCP-01.md). **Estimate:** 1 hour.
