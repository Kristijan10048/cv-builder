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

**Depends on:** None. **Estimate:** 2 hours.
