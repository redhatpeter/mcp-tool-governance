# MCP Tool Governance

Governance plane for MCP (Model Context Protocol) tools published through
Azure API Management. Enforces canonical naming, alias rewriting, JWT
validation, and rate limiting at the APIM edge — no custom MCP server
containers required.

## Status

PoC. Architecture is stable. **L1 (design-time lint) and L2 (similarity CI gate
+ ingest-on-merge) are shipped and live against Azure OpenAI + Azure AI Search.**
L3 (runtime canonical rewrite at the APIM gateway) has a working smoke build —
see `apim/policies/canonical-rewrite-smoke.policy.xml` and Act 3 of the demo.

Snapshot of what's running:

| Layer | Where | What |
|---|---|---|
| L1 | [`.github/workflows/validate-mcp-tools.yml`](.github/workflows/validate-mcp-tools.yml) | `tools-cli/lint.py` blocks bad operations at PR time. |
| L2 | [`.github/workflows/similarity-check.yml`](.github/workflows/similarity-check.yml) | `apps/dup-resolver/check_pr.py` embeds new ops, queries `mcp-tool-fingerprints`, posts a verdict on the PR. Threshold = repo variable `CLUSTER_THRESHOLD` (this repo overrides to `0.92`). |
| L2 | [`.github/workflows/ingest-on-merge.yml`](.github/workflows/ingest-on-merge.yml) | On every push to `main`, re-ingests `apim/openapi/*.json` and **deletes stale docs** so the index never drifts. |
| L3 | [`apim/policies/canonical-rewrite-smoke.policy.xml`](apim/policies/canonical-rewrite-smoke.policy.xml) | MCP-server-scoped policy — three live aliases rewrite to `financeQuoteGet`. |
| Demo | [`demo/run-demo.sh`](demo/run-demo.sh) | 5-minute push-button walkthrough. Pre-captured fallback at [`docs/samples/demo-transcript.md`](docs/samples/demo-transcript.md). |

Open work tracked in [`docs/todo.md`](docs/todo.md).

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

- APIM: `<apim-instance>` (gateway: `https://<apim-gateway-host>`)
- Reused: AI Search `ai102srch193837986`, Cosmos `cosmos-ws`, existing Azure OpenAI
- New RG for PoC: `MCP-tool-governance`

See ARCHITECTURE.md §17 for the three-week PoC plan.
