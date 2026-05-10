# MCP Tool Governance

Governance plane for MCP (Model Context Protocol) tools published through
Azure API Management. Enforces canonical naming, alias rewriting, JWT
validation, and rate limiting at the APIM edge — no custom MCP server
containers required.

## Status

PoC complete. **All three layers shipped and live** against the
`apimopenai99` APIM instance + Azure OpenAI + Azure AI Search + Cosmos.

Snapshot of what's running:

| Layer | Where | What |
|---|---|---|
| L1 | [`.github/workflows/validate-mcp-tools.yml`](.github/workflows/validate-mcp-tools.yml) | `tools-cli/lint.py` blocks bad operations at PR time. |
| L2 | [`.github/workflows/similarity-check.yml`](.github/workflows/similarity-check.yml) | `apps/dup-resolver/check_pr.py` embeds new ops, queries `mcp-tool-fingerprints`, posts a 5-tier verdict (DUPLICATE / WARN / REVIEW / OK / INFO) on the PR. Thresholds = repo variables `CLUSTER_THRESHOLD` (`0.92`) + `REVIEW_THRESHOLD` (`0.65`). |
| L2 | [`.github/workflows/ingest-on-merge.yml`](.github/workflows/ingest-on-merge.yml) + [`daily-ingest.yml`](.github/workflows/daily-ingest.yml) | Re-ingest `apim/openapi/*.json` on every push to `main` and nightly; reconciles AI Search + Cosmos `mcp-canonical-map` (deletes stale docs). |
| L3 | [`apim/policies/canonical-rewrite.policy.xml`](apim/policies/canonical-rewrite.policy.xml) + [`tools-list-filter.policy.xml`](apim/policies/tools-list-filter.policy.xml) | Both deployed on `governed-mcp` and `messy-mcp`. Live evidence: `x-mcp-tools-filtered: 3` on `messy-mcp/tools/list`; `x-mcp-canonical-rewrite: createCustomer -> customerCreate` on `tools/call`. |
| CI gate | [`.github/workflows/policy-tests.yml`](.github/workflows/policy-tests.yml) | 6 unit tests (wirename + verdict-tier) + 8 Cosmos contract replays. Latest green: [run 25637828620](https://github.com/redhatpeter/mcp-tool-governance/actions/runs/25637828620). |
| Demo | [`demo/run-demo.sh`](demo/run-demo.sh) | 5-minute push-button walkthrough. Pre-captured fallback at [`docs/samples/demo-transcript.md`](docs/samples/demo-transcript.md) with a 2026-05-10 addendum covering L3 deploy + REVIEW tier + CI + the APIM-MCP body-forwarding caveat. |

**Known external blocker (not our bug):** APIM-MCP currently forwards only
the last property of `params.arguments` as a raw scalar to the backend
(regression of `release-service-2026-03`). Tracked at
[Azure-Samples/AI-Gateway#315](https://github.com/Azure-Samples/AI-Gateway/issues/315);
drafts ready under [`docs/external/`](docs/external/). Reproduces with all
custom policies stripped — governance layer is innocent.

Open work tracked in [`docs/todo.md`](docs/todo.md). Post-implementation
reflections + investments needed before pilot in
[ARCHITECTURE.md §24.A](docs/ARCHITECTURE.md#24a-appendix--post-implementation-reflections-2026-05-10).

## Documentation

| Document | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Source of truth — design + 3-week PoC plan (26 sections). |
| [docs/ARCHITECTURE-diagrams.md](docs/ARCHITECTURE-diagrams.md) | Mermaid + draw.io diagrams. |
| [docs/adr/0001-apim-mcp-native.md](docs/adr/0001-apim-mcp-native.md) | Why we use APIM-MCP instead of custom MCP servers. |
| [docs/adr/0002-repo-split.md](docs/adr/0002-repo-split.md) | Why this repo exists separately from `agent-framework`. |
| [docs/adr/0003-topology-upgrade-path.md](docs/adr/0003-topology-upgrade-path.md) | Staged path: B (PoC) → D (pilot) → E (Year 1) → G (only if forced). |
| [docs/eval/precision-recall.md](docs/eval/precision-recall.md) | Threshold sweep over the 76-pair labeled set; defends the 0.92 / 0.65 ladder. |
| [docs/handoffs/](docs/handoffs/) | Per-session handoff notes (one file per session, dated). Latest: [2026-05-10](docs/handoffs/2026-05-10.md). |

## Repository layout (actual)

```
.
├── apim/
│   ├── deploy/            # Python deploy script for L3 policies (idempotent)
│   ├── openapi/           # finance-governed.json + finance-messy.json (the spec source)
│   └── policies/          # L3 policy XML — canonical-rewrite + tools-list-filter
├── apps/
│   └── dup-resolver/      # L2 — embed, cluster, elect, write canonical_map (+ FastAPI for demo)
├── demo/                  # 5-minute push-button walkthrough script
├── docs/                  # ARCHITECTURE.md, ADRs, handoffs, eval reports, lessons, external drafts
├── eval/                  # before/after harness (governed vs messy, +30pp lift on pre-L3 data)
├── tools-cli/             # L1 lint (tools-cli/lint.py)
└── .github/workflows/     # validate-mcp-tools, similarity-check, ingest-on-merge,
                           # daily-ingest, policy-tests
```

> Not present (and not needed for the PoC): `infra/terraform/`,
> `registry/`, `profiles/`, `apps/frontend/`. These are listed as Year-1
> investments in [ARCHITECTURE.md §24](docs/ARCHITECTURE.md) (and §24.A
> for post-implementation reflections).

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
