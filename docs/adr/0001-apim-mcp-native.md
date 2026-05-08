# ADR 0001 — Use APIM-MCP natively instead of custom MCP servers

- **Status:** Accepted
- **Date:** 2026-05-08
- **Supersedes:** v2 PoC plan ("custom MCP servers behind an APIM aggregator")

## Context

The v2 design ran two custom MCP server containers (Backend A, Backend B) on Azure
Container Apps, fronted by a custom APIM "aggregator" API that fanned requests out to
them. APIM was effectively a reverse proxy; all governance logic (auth, naming,
canonical rewrite, election application) lived inside container code we owned.

Since v2 was drafted, Azure API Management shipped the **APIM-MCP** capability:
any imported REST API gets a native `/mcp` endpoint that exposes its operations as
MCP tools, and policy can be attached at the **MCP-server scope** (Portal: *APIs →
MCP Servers → \<server\> → MCP → Policies*).

## Decision

Adopt APIM-MCP as the MCP server runtime. Each business domain gets one imported
REST API in APIM with its `/mcp` endpoint enabled. All L3 enforcement (JWT
validation, rate limiting, canonical-name rewrite via Cosmos lookup, audit
headers) is implemented as MCP-server-scoped APIM policy. No custom MCP server
containers are deployed.

## Consequences

**Positive**

- Container Apps footprint drops from 5 to 2 (Frontend + Dup-Resolver only).
- Auth (`validate-jwt`), throttling (`rate-limit`), and canonical rewrite all
  happen at the edge — no per-language SDK to maintain.
- Cosmos access uses APIM's system-assigned managed identity
  (`authentication-managed-identity`) plus the `Cosmos DB Built-in Data Reader`
  role on the `mcp-canonical-map` container. **No keys in Key Vault for this path.**
- PoC monthly cost falls from ~$100 to ~$80.
- Policy is versionable via APIM Policy Fragments (see ADR 0003 / Architecture §24 #10).

**Negative / accepted**

- APIM-MCP currently supports MCP **tools only** — not `resources` or `prompts`.
  These are out of scope for the PoC. If they become must-have and APIM-MCP still
  lacks support, add a thin custom shim **only for those types** — never for tools.
- Debugging moves from container logs to APIM trace + App Insights, which is a
  shift in operator skill.

## References

- Architecture §4 (request walk-throughs), §15 (full policy XML), §24 #10
- HANDOFF.md "What was decided this session" #1, #2, #3
