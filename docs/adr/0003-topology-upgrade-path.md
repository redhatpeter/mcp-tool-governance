# ADR 0003 — Staged topology upgrade path (B → D → E → G)

- **Status:** Accepted
- **Date:** 2026-05-08

## Context

[ARCHITECTURE.md §4.1](../ARCHITECTURE.md) evaluates seven topology options
(A–G) for how MCP servers, APIM products, and governance map onto APIM
instances. The PoC needs to pick a starting point without painting future
pilots and production into a corner.

## Decision

Adopt a staged path:

| Stage | Topology | What it adds |
|---|---|---|
| **PoC** | **B** — one MCP server per business domain, single APIM instance | Smallest viable surface to demonstrate L3 enforcement and canonical rewrite. |
| **Pilot** | **D** — Option B + a permanent `<domain>-raw/mcp` internal-only APIM Product per domain | Gives teams day-zero callability before L2 election decides a canonical name. `<domain>-raw/mcp` is **operational furniture, not a demo prop**. |
| **Year 1** | **+ E** — per-profile (audience-scoped) MCP servers layered on top of D | Lets us expose curated tool subsets to specific consumer profiles without forking the canonical map. |
| **Year 2+** | **G** — multi-APIM federation | **Only** if forced by data-residency, blast-radius isolation, or per-BU billing requirements. Default is to stay on a single APIM. |

The `messy/mcp` server in the PoC is a **demo prop only** — it exists to
exhibit the four failure modes and is dropped after the PoC. Do not confuse
it with `<domain>-raw/mcp`, which is permanent.

## Consequences

**Positive**

- Every stage is a strict superset of the previous one — no rip-and-replace.
- Policy Fragments (per ADR 0001 / Architecture §24 #10) make the D → E jump
  cheap because shared policy is centralized.
- Defers the multi-APIM complexity of G until there's a concrete forcing
  function.

**Negative / accepted**

- The B → D transition introduces a new permanent APIM Product type
  (`<domain>-raw`) that operators must learn. Documented in §4.1 and §24 #12.
- E requires careful audience claim design in JWTs; we will not invest in
  that until pilot is stable.

## References

- Architecture §4.1 (full 7-option table, 13-criterion evaluation, ASCII ladder)
- Architecture §24 #0, #10, #12
- ADR 0001 (APIM-MCP native — prerequisite for cheap policy fragments)
