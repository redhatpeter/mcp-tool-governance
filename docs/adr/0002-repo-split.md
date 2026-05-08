# ADR 0002 — Split MCP governance work into its own repository

- **Status:** Accepted
- **Date:** 2026-05-08

## Context

The MCP Tool Governance PoC was originally scaffolded inside
`microsoft/agent-framework` at `backup/aon/mcp/`. That location had several
problems:

- `poc/` was a self-contained product (its own `.github/`, `.gitignore`,
  `docker-compose.yml`) sitting three levels deep in someone else's repo.
- The framework repo is public OSS. Customer-specific identifiers
  (Aon, `apim-btss-eastus2-dev`, `gateway.dev.btss.eastus2.azure.aon.com`)
  must not be pushed upstream.
- GitHub Actions only run from root-level `.github/workflows/`, so the nested
  workflows were inert.
- Cannot tag releases, restrict reviewers, or enforce CODEOWNERS for a nested
  subtree.

## Decision

Extract `backup/aon/mcp/` into a private, Aon-owned repository
(`mcp-tool-governance`) with `poc/` contents promoted to repo root. The
`agent-framework` fork no longer carries Aon-specific MCP work.

## Consequences

**Positive**

- Workflows, CODEOWNERS, branch protection, and release tags now work normally.
- No risk of leaking customer identifiers upstream.
- Doc layout is flatter: `docs/ARCHITECTURE.md` instead of
  `backup/aon/mcp/MCP-Tool-Governance-POC-Plan-v3.md`.

**Negative / accepted**

- Loss of single-clone convenience for engineers who want to read framework
  source alongside the PoC. Mitigated by a multi-root VS Code workspace
  (see HANDOFF.md "Multi-root VS Code workspace" snippet).
- History rewrite via `git filter-repo` was performed during migration; the
  new repo's first commit is the squashed root.

## References

- HANDOFF.md "Open decisions" #1
- ADR 0001 (which made the v2 → v3 simplification that triggered this cleanup)
