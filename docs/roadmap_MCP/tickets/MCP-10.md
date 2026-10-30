# MCP-10: Document setup and troubleshooting

**Status:** Pending.
**Summary:** Explain how to run CV Builder and connect its read-only MCP server.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Complete the package README with Windows PowerShell commands for creating the
   isolated environment, installing the pinned dependencies, running tests, and
   launching python -m applykit_mcp.
2. Show how to start the existing CV Builder application separately with Uvicorn,
   then configure APPLYKIT_MCP_API_URL and APPLYKIT_MCP_REQUEST_TIMEOUT_SECONDS.
   Explain that the stdio process waits for a client and opens no MCP HTTP port.
3. Include the labeled local-host configuration, tested Inspector CLI procedure, and synthetic
   examples of overview, filtered history, application detail, and stored-job
   listing. Explain how to find an application identifier before retrieving it.
4. Document troubleshooting for interpreter/module paths, missing dependencies,
   invalid configuration, wrong API port, unavailable application, timeout,
   handshake issues, and incompatible API responses. Direct diagnostics to stderr.
5. State the exact tested versions, read-only scope, field exclusions, and the
   application-list API's unpaginated retrieval limitation. Explain that stored
   jobs are not fetched afresh and that generation/write tools are future work.
6. Describe safe test setup using disposable databases/log locations, and clarify
   that connecting a host makes returned application data available to that host.

**Deliverable:** Complete setup, configuration, usage, and troubleshooting guide.

**Done when:** A fresh environment can follow the guide, run the tests and
Inspector CLI script, and use all four tools against a disposable CV Builder instance.
No step assumes production database access or claims untested host compatibility.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-10-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/README.md`
- `mcp_server/docs/verification.md`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
.\mcp_server\.venv-integration\Scripts\python.exe -m pytest .\mcp_server\tests
~~~

Follow the README from a fresh environment and rerun the Inspector CLI command. Ensure every stated version/result was observed; distinguish optional desktop-host verification and future always-on service deployment.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** [MCP-09](MCP-09.md). **Estimate:** 1 hour.
