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

- [ ] **CI cold-start budget documentation**
  Local script-cold elapsed: 1 op = 6.7s, 5 = 7.6s, 20 = 12.1s. CI
  runner spin-up adds ~30s on top. Document expected end-to-end CI time
  in `apps/dup-resolver/README.md` so reviewers know what "normal"
  looks like and what to investigate when a run takes 5×.

- [ ] **Daily cron `ingest.py` as belt-and-braces backup**
  `ingest-on-merge` covers the happy path. If a run fails (AOAI quota,
  AAD outage), the index drifts until next merge. Add a scheduled
  workflow (`cron: '17 4 * * *'`) that runs `ingest.py` and posts a
  short summary to the workflow run page. Same secrets, same step.

- [ ] **Index freshness alert threshold**
  The verdict footer now reports oldest `last_seen_utc`. Add a soft
  alert: if `(now - oldest) > 24h`, render the footer in **bold** and
  prepend "⚠️ stale index" so reviewers don't trust the score blindly.

## P2 — polish

- [ ] **Threshold sweep in PR comment**
  The verdict table shows the score at the configured threshold only.
  For borderline candidates (WARN, or DUPLICATE close to threshold),
  optionally post a PR comment with the threshold sweep
  (0.85 / 0.88 / 0.92 / 0.96) so reviewers can see how the verdict
  would shift if the org tightened or loosened.

- [ ] **PR comment with top-3 nearest neighbors**
  Verdict markdown table only shows the top match. The full top-3 list
  is already captured in `result.nearest`; render it as a collapsible
  `<details>` block so reviewers can spot near-ties between candidates.

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

- [ ] **Spec source plurality**
  Today `openapi_source.SERVER_BY_FILE` is a hard-coded mapping of
  filename → server name. Generalize to read a manifest
  (`apim/openapi/_servers.yaml`) so adding a new MCP server doesn't
  require a code change.
