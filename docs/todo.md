# TODO

Open work items for the MCP Tool Governance POC. Grouped by priority.
Last updated: 2026-05-10 — second sweep: closed PR #1, shipped rename
detection + freshness signal + multi-file test scenario, bumped action
versions, refreshed demo transcript and threshold docs.

## ✅ Recently completed (2026-05-10)

- ✅ `ingest-on-merge` workflow (Option A — index reconciliation) — commit `12e865a`
- ✅ PR-time deletion-aware filter (rename → INFO verdict)
- ✅ Multi-file PR test scenario in `apps/dup-resolver/tests/run_scenarios.sh`
- ✅ Index freshness signal in verdict markdown footer
- ✅ Bumped `actions/checkout@v5` + `actions/setup-python@v6` (Node 24)
- ✅ Documented `CLUSTER_THRESHOLD` policy in `apps/dup-resolver/README.md`
- ✅ Refreshed `docs/samples/demo-transcript.md` Act 4 to the 0.92 / 0.958 verdict
- ✅ Closed PR #1 with summary comment, deleted branch
- ✅ Stale-index alert (>24h → bold ⚠️ banner in `check_pr.py` footer)
- ✅ `daily-ingest.yml` nightly backstop (04:17 UTC, same concurrency group)
- ✅ Performance budget + index-hygiene tiers documented in dup-resolver README
- ✅ ARCHITECTURE.md §14 backfilled with implementation-drift callout
- ✅ Top-3 nearest neighbors as collapsible `<details>` per non-OK row
- ✅ Threshold sweep table per non-OK row (0.85 / 0.88 / 0.92 / 0.95 + current)
- ✅ Spec-source manifest (`apim/openapi/_servers.yaml`) replaces hard-coded `SERVER_BY_FILE`
- ✅ Lint integration with manifest — new rule **E007** (spec stem must be declared)
- ✅ Manifest `unmanaged:` list + lint exemption — fixes pre-existing CI failure on demo prop

## P0 — operational gaps that will bite us next demo

- [ ] **OIDC migration for CI → Azure**
  CI uses `AOAI_API_KEY` + `SEARCH_ADMIN_KEY` repo secrets. Azure Policy
  `CognitiveServices_LocalAuth_Modify` will eventually re-disable key
  auth on `common-open-ai`, breaking the gate. Migrate to GitHub OIDC →
  federated credential → AAD-only auth (`DefaultAzureCredential` already
  supported in `apps/dup-resolver/config.py`). Steps:
  1. Create Entra app registration + federated credential bound to
     `repo:redhatpeter/mcp-tool-governance:ref:refs/heads/main` and
     PR refs (`pull_request`).
  2. Grant `Cognitive Services OpenAI User` on the AOAI account and
     `Search Index Data Contributor` + `Search Service Contributor` on
     the search service.
  3. Add `permissions: id-token: write` and `azure/login@v2` to all
     three workflows; drop the secrets, keep only `AZURE_CLIENT_ID` /
     `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` as repo variables.
  4. Verify by re-running each workflow with key auth disabled.

  Currently deferred — owner has key auth re-enabled and is willing to
  keep it that way. Revisit when Azure Policy enforcement tightens.

## P1 — gaps that would improve operability

- [ ] **Trigger and observe a `daily-ingest` cron run end-to-end**
  Workflow lands today; first scheduled fire is 04:17 UTC tomorrow.
  Validate with `gh workflow run daily-ingest.yml` once, confirm
  reconciliation summary renders, and document the link in next
  session's handoff.

- [ ] **Backfill ARCHITECTURE.md §14 with the implementation drift**
  Design doc still describes L2 as the FastAPI service. Real impl is
  `check_pr.py` for CI + service for demo. Add a callout pointing to
  `apps/dup-resolver/README.md` so readers don't go looking for
  `/similarity` in CI.

## P2 — polish

_All P2 items complete in this session. Track new polish items here as
they surface._

## P3 — exploration / future work

- [ ] **MCP-side enforcement (L3)**
  L1 (lint) and L2 (similarity CI) are design-time. L3 — runtime
  enforcement via the MCP gateway / APIM policy — is sketched in
  `docs/ARCHITECTURE.md` §3.4 but not implemented. Would close the
  loophole where a duplicate slips through both L1 and L2 (e.g. via a
  force-merge, or via a new MCP server added outside the PR flow).

- [ ] **Quantitative precision/recall study**
  Build a labeled set of 30–50 known-duplicate vs known-novel pairs
  from real-world MCP servers (or curated synthetic ones), and report
  precision/recall per threshold. Would let us defend the 0.88 vs 0.92
  choice with a number, not a vibe — and inform a future "auto-tune
  threshold per organization" feature.

- [ ] **Spec source plurality** — **complete**. Manifest at
  `apim/openapi/_servers.yaml` is now the source of truth, and
  `tools-cli/lint.py` enforces it via E007 (unknown stems fail the
  PR). Leave this entry until a new server is added in anger to
  confirm the workflow.
