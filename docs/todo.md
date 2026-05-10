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
- ✅ Precision/recall scaffold — labeled set + sweep evaluator + first report
- ✅ Fingerprint variant A/B harness (`--compare`, 5 shapes) — production fingerprint kept
- ✅ L3 step 1 — canonical_map writer (Cosmos `governance.mcp-canonical-map`)
- ✅ L3 step 2 — `tools/list` filter policy + writer schema enrichment (primary, aliases)
- ✅ L3 step 3 — `tools/call` rewrite for unified schema + Python validation harness
- ✅ L3 step 4 — `COSMOS_ENDPOINT`/`COSMOS_KEY` wired into ingest CI
- ✅ OIDC migration for AOAI — forced by `CognitiveServices_LocalAuth_Modify` policy on `common-open-ai`. Workflows now use `azure/login@v2` + federated credential. AOAI key auth retired in CI.
- ✅ `daily-ingest` end-to-end smoke (run [25631367436](https://github.com/redhatpeter/mcp-tool-governance/actions/runs/25631367436))
- ✅ L3 policies deployed to APIM (`governed-mcp`, `messy-mcp`) via `apim/deploy/deploy_l3_policies.py`
- ✅ Wire-name resolver (`apim_wirenames`) — ingest reads `properties.mcpTools[].{name, operationId}` from APIM as the source of truth; canonical_map keys now match runtime `tools/list` names. Smoke on `messy-mcp`: 3 dropped, 10 kept (`x-mcp-tools-filtered: 3`).
- ✅ L3 E2E smoke green (commit `85c3c26`) — 6/6 assertions across both servers, including `governed-mcp` 500 root-caused to `cache-store-value` rejecting empty string (sentinel fix landed in `tools-list-filter.policy.xml`).
- ✅ CI gate (`.github/workflows/policy-tests.yml`, run `25637397605`) — `unit-tests` job runs `test_wirename_resolution.py` (3/3) and `policy-contract` job replays `validate_policies.py` against live Cosmos (8/8). Triggers on changes to `apps/dup-resolver/{canonical_map,openapi_source,apim_wirenames,ingest}.py`, `apim/policies/**`, `apim/deploy/**`, the workflow itself, and `workflow_dispatch`.- \u2705 Two-tier verdict (`REVIEW` band) added to `check_pr.py` (commit pending). Hard-block at `CLUSTER_THRESHOLD` unchanged; new `REVIEW_THRESHOLD` (default `0.65`, env-overridable) catches real-world cross-vendor semantic duplicates surfaced by the expanded labeled set without failing the check. Regression test at `tests/test_verdict_tiers.py` wired into the `unit-tests` CI job. README + path triggers updated.
## P0 — operational gaps that will bite us next demo

_All P0 items closed in this session._

## P1 — gaps that would improve operability

_All P1 items closed in this session._

## P2 — polish

- [ ] **External blocker: APIM-MCP body forwarding (tracked at [Azure-Samples/AI-Gateway#315](https://github.com/Azure-Samples/AI-Gateway/issues/315))**
  On `tools/call`, APIM-MCP forwards only the **last property's raw
  scalar** as the backend HTTP body instead of constructing a JSON
  object from `params.arguments`. Confirmed regression of the fix
  shipped in [release-service-2026-03][rs26-03] (which replaced the
  prior empty-body symptom from MS Q&A 4371821 / 5597117). Reproduces
  with **all custom policies stripped** from the MCP server, so
  governance is provably innocent. Demo impact: backend always
  returns `json_invalid` on `tools/call`, but the L3 governance
  layer's behavior is fully observable via `x-mcp-canonical-rewrite`
  and `x-mcp-tools-filtered` response headers regardless. No
  user-space workaround works post-fix (envelope is consumed upstream
  of both MCP-server and source-API policy chains). Awaiting MS
  triage on issue #315 / support ticket.

[rs26-03]: https://github.com/Azure/API-Management/releases/tag/release-service-2026-03

## P3 — exploration / future work

- [ ] **MCP-side enforcement (L3) — runtime rewriting**
  L1 (lint) and L2 (similarity CI) are design-time. L3 — runtime
  enforcement via the MCP gateway / APIM policy — is sketched in
  `docs/ARCHITECTURE.md` §3.4 but not implemented.
  - [x] **L3 step 1** — canonical_map writer. L2 now persists each
    election to Cosmos `governance.mcp-canonical-map` (one doc per
    cluster, partitioned by `/canonical_id`). Writer is optional-by-
    default — empty `COSMOS_ENDPOINT` no-ops; AAD or key auth.
    Reconcile mirrors the AI Search ghost-doc cleanup.
  - [x] **L3 step 2** — APIM `tools/list` filter policy authored at
    `apim/policies/tools-list-filter.policy.xml`. Reads `aliases` from
    canonical_map (cached 60s), drops every alias from outbound
    `tools/list` response, adds `x-mcp-tools-filtered` header. Writer
    enriched with `primary` + `aliases` projection fields so both the
    new policy and the existing `canonical-rewrite.policy.xml` consume
    the same docs. **Not yet deployed** — attach via Portal per server.
  - [x] **L3 step 3** — `canonical-rewrite.policy.xml` rewritten for
    the unified schema. Synthesizes `<server>__<wire>` fqid, queries
    `c.id = @id OR ARRAY_CONTAINS(c.aliases, @id)`, returns
    `c.primary.name`. Validation harness at
    `apps/dup-resolver/tests/validate_policies.py` replays both policy
    queries against live Cosmos — 9/9 assertions pass on the demo data
    (3 alias resolutions, 1 already-canonical, 1 singleton, 1 unknown
    fail-open, plus 2 tools/list drop-set cases). **Not yet deployed.**
  - [x] **L3 step 4** — wire `COSMOS_ENDPOINT` + `COSMOS_KEY` into
    `ingest-on-merge.yml` and `daily-ingest.yml`. Repo variable
    `COSMOS_ENDPOINT` + repo secret `COSMOS_KEY`. Local auth was
    re-enabled on `cosmoslab82658` for this (Azure Policy is `audit`
    only on this account, so it sticks). Workflow summary now
    surfaces the `canonical_map: {written, deleted, disabled,
    failures}` block from ingest's run summary.

- ✅ **Quantitative precision/recall — labeled set grown to 76 pairs**
  Scaffold at `apps/dup-resolver/tests/labeled_pairs.yaml`
  (**76 pairs** — 26 in-repo + 50 real-world from canonical
  `modelcontextprotocol/servers` plus widely-used third-party MCP
  servers: github, gitlab, linear, jira, notion, confluence, slack,
  discord, dropbox, gdrive, postgres, mysql, sqlite, redis, memcached,
  aws-s3, gcs, kubernetes, helm, docker, sentry, rollbar, stripe,
  square, playwright, puppeteer, fetch, brave-search, memory).
  Evaluator at `apps/dup-resolver/eval_threshold.py` (sweep +
  `--compare` over 5 fingerprint variants), report at
  `docs/eval/precision-recall.md` (215 lines).
  **2026-05-10 final finding:** at the production threshold 0.92,
  precision remains **1.000** on 76 pairs (43 novels, 0 false
  positives) — the hard-block is robust. Recall at 0.92 is 9 %; the
  REVIEW band at 0.65 recovers ~64 % of duplicates as soft "review
  recommended" surfaces in PR comments. No fingerprint variant
  perfectly separates the two classes; `combined` actually has the
  worst separability on the larger set (margin −0.312) because
  same-domain-novel scores rise faster than true-duplicate scores
  when vendor diversity grows. Production fingerprint stays at
  `baseline`. The two-tier verdict is the correct architectural fix
  for this regime.
  *Marginal value of further growth:* see report's "Where to grow
  next" section — primarily action-verb-divergent cross-vendor
  duplicates and more generic-name pairs.
