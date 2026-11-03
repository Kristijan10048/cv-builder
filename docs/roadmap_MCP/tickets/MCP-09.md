# MCP-09: Automate Inspector verification

**Status:** Pending.
**Summary:** Verify the CV Builder tools through the scriptable MCP Inspector CLI.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Start a disposable CV Builder instance from the integration-test fixtures
   on a loopback port and point CV_BUILDER_MCP_API_URL at that instance.
2. Select and record an exact MCP Inspector version and its required Node version.
   Add a repeatable PowerShell smoke script using Inspector's CLI mode; pass the
   installed package's absolute Python path and module launch arguments.
3. Discover the four tools, check schemas, and invoke each using synthetic fixture
   filters and identifiers. Also invoke an unknown application and verify a
   subsequent valid request succeeds. MCP-08 covers recovery within one session;
   separate CLI invocations must not be claimed to prove session continuity.
4. Capture exit status and parsed results. A tool execution error is an expected
   outcome only in its explicit negative test. Stop the disposable application,
   verify the unavailable-app error, restart it, and verify another successful call.
5. Provide a clearly labeled generic stdio launch example with interpreter,
   module arguments, environment values, and installation prerequisites.
   Desktop-host-specific verification is optional: if a host is available, record
   its exact version and results; otherwise label the example unverified. Do not
   require a signed-in desktop host to complete the automatic checks.

**Deliverable:** Repeatable Inspector CLI smoke script, exact tool versions,
machine-readable results, and a labeled local-host configuration example.

**Done when:** The Inspector CLI discovers all four tools, calls each successfully,
and checks the defined negative cases using disposable data. Required tooling
is versioned; failed checks return a nonzero script exit code; helper processes
are cleaned up. Any optional desktop-host verification is accurately labeled.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-09-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/scripts/Verify-Inspector.ps1`
- `mcp_server/tools/package.json`
- `mcp_server/tools/package-lock.json`
- `mcp_server/docs/stdio-launch.example.json`
- `mcp_server/docs/verification.md`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\scripts\Verify-Inspector.ps1 -McpPythonPath (Resolve-Path .\mcp_server\.venv\Scripts\python.exe).Path -ApplicationPythonPath (Resolve-Path .\mcp_server\.venv-integration\Scripts\python.exe).Path
~~~

Run the guide's pinned npm installation first. Use the disposable application helper, check actual result JSON and exit codes, and distinguish separate CLI invocations from same-session SDK checks.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-08](MCP-08.md). **Estimate:** 1 hour.
