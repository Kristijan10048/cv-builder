# MCP-01: Define the CV Builder tool contract

**Status:** Pending.
**Summary:** Specify four read-only MCP tools using the existing CV Builder API.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Inspect the current routes in [app/main.py](../../../app/main.py) and
   [app/job_search.py](../../../app/job_search.py), including the existing
   response serializers and input validation.
2. Record input/output schemas for get_overview, list_applications,
   get_application, and list_available_jobs, following the roadmap's tool contract.
3. Include synthetic request/response examples for populated and empty results,
   unknown application/preference identifiers, malformed arguments, and an
   unavailable application. Document the HTTP-to-tool error mapping.
4. Define field allowlists, strict integer validation, query limits, application
   pagination inside the adapter, and preservation of stored-job API pagination.
5. Record the standalone HTTP-adapter architecture and module/package layout.
   Separate proposed MCP behavior from behavior already provided by CV Builder.

**Deliverable:** A versioned contract document in the future MCP package, including
the endpoint map, model fields, examples, error behavior, and initial exclusions.

**Done when:** Every tool has a complete schema and examples; application searches
preserve API filter semantics; known API limits are explicit; the contract excludes
writes, generation, job fetching, personal-profile access, raw HTML, imported
payloads, and tailored-document content. Review it against the actual routes.

## Coding-agent handoff

Read [the execution guide](../coding_agent_execution.md) and [this ticket's short summary](../summaries/MCP-01-summary.md).
File paths below are planned outputs relative to the CV Builder project root.

**File targets:**

- `mcp_server/docs/tool_contract.md`
- `mcp_server/docs/contract_examples.json`

**Focused validation** (PowerShell, from the CV Builder root, after prerequisite setup):

~~~powershell
Get-Content -LiteralPath .\mcp_server\docs\contract_examples.json -Raw | ConvertFrom-Json | Out-Null
~~~

Compare every field and mapped route with the current application code. Include empty-result, invalid-input, not-found, and unavailable-API examples.

**Handoff result:** Report changed files, commands actually run, outcomes, and any
unmet acceptance criteria. Mark this ticket complete only after its required
checks pass; keep this ticket, roadmap, and summary consistent.

**Depends on:** None. **Estimate:** 2 hours.
