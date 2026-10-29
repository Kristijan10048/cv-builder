# MCP-06: Expose application history tools

**Status:** Pending.
**Summary:** Let MCP clients find saved CV Builder applications and inspect one application's details.

[Development roadmap](../mcp_server_roadmap.md) | [Original brief](../mcp_server.md)

## Implementation steps

1. Register list_applications with typed search/status filters and page controls.
   Use the roadmap's defaults and limits; preserve the existing search/status
   behavior rather than restricting status to a new enum.
2. Return summary fields and the adapter's page envelope. Explain in the tool
   description that it reads application history rather than fetching job listings.
3. Register get_application with a strict positive integer application_id.
   Return summary fields, job_description, and notes only. Omit raw_html,
   imported_data, adjusted_cv, and adjusted_cover_letter.
4. Map adapter errors to concise tool execution errors using the pinned SDK.
   Reject missing/unknown arguments, booleans, strings for integer inputs,
   invalid page sizes, and nonpositive identifiers through input validation.

**Deliverable:** Two registered application tools, structured output schemas,
descriptions, and client-level tests.

**Done when:** Tests cover filtered history, custom stored status values, empty
history, multiple pages, excessive-page clamping, a known application, an unknown
application, malformed input, and recovery with a successful call after failure.
Excluded fields never appear in tool responses, and calls make no mutations.

**Depends on:** [MCP-05](MCP-05.md). **Estimate:** 3 hours.
