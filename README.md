# MCP Tool Governance

Governance plane for MCP (Model Context Protocol) tools published through
Azure API Management. Enforces canonical naming, alias rewriting, JWT
validation, and rate limiting at the APIM edge — no custom MCP server
containers required.

## Status

PoC. Architecture is stable; code build-out has not started.

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Source of truth — design + 3-week PoC plan (26 sections). |
| [docs/ARCHITECTURE-diagrams.md](docs/ARCHITECTURE-diagrams.md) | Mermaid + draw.io diagrams. |
| [docs/adr/0001-apim-mcp-native.md](docs/adr/0001-apim-mcp-native.md) | Why we use APIM-MCP instead of custom MCP servers. |
| [docs/adr/0002-repo-split.md](docs/adr/0002-repo-split.md) | Why this repo exists separately from `agent-framework`. |
| [docs/adr/0003-topology-upgrade-path.md](docs/adr/0003-topology-upgrade-path.md) | Staged path: B (PoC) → D (pilot) → E (Year 1) → G (only if forced). |
| [docs/handoffs/](docs/handoffs/) | Per-session handoff notes (one file per session, dated). Latest: [2026-05-08](docs/handoffs/2026-05-08.md). |

## Repository layout (target)

Built out as work progresses; empty directories are not pre-created.

```
.
├── docs/                  # design, diagrams, ADRs (present)
├── apim/policies/         # canonical-rewrite policy XML (PoC week 1)
├── infra/terraform/       # APIM, Cosmos role assignment, AI Search index, etc. (PoC week 1)
├── registry/
│   ├── governed/          # canonical tool definitions (PoC week 1)
│   └── messy/             # demo prop — failure-mode exhibits (dropped post-PoC)
├── profiles/              # consumer audience profiles (PoC week 2)
├── apps/
│   ├── frontend/          # Container App (PoC week 2)
│   └── dup-resolver/      # Container App (PoC week 2)
├── tools-cli/             # registry validation + canonical-map sync (PoC week 1)
├── eval/                  # eval harness — to be replaced by AI Foundry Evaluations (PoC week 3)
└── .github/workflows/     # validate-tools.yml, deploy-mcp.yml (PoC week 1)
```

## Key conventions

- **Naming standard:** `domain.entity.action` for canonical IDs,
  `domain_entity_action` for runtime tool names. Regex
  `^[a-z][a-z0-9_]{2,63}$`.
- **Canonical map fields:** `primary` (singular) and `aliases` (plural). Do not
  rename.
- **Runtime governance signal:** the `x-mcp-canonical-rewrite` response header
  is stamped by APIM policy on alias hits and surfaced in App Insights.

## Target Azure environment

- APIM: `apim-btss-eastus2-dev` (gateway: `https://gateway.dev.btss.eastus2.azure.aon.com`)
- Reused: AI Search `ai102srch193837986`, Cosmos `cosmos-ws`, existing Azure OpenAI
- New RG for PoC: `MCP-tool-governance`

See ARCHITECTURE.md §17 for the three-week PoC plan.
