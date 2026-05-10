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

## P0 — operational gaps that will bite us next demo

_All P0 items closed in this session._

## P1 — gaps that would improve operability

- [ ] **Diagnose `governed-mcp` 500 on `tools/list`**
  With the L3 policy *removed entirely*, `POST /governed-mcp/mcp` still
  returns HTTP 500. Pre-existing in the API itself (backend or
  MCP-typed wiring), unrelated to L3. Repro:
  `curl -X POST .../governed-mcp/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`.
  Trace via APIM `listDebugCredentials` → `listTrace`. Likely places to
  look first: backend service URL, `mcp-server` policy, MI on the
  source `finance-api-governed` API.

- [ ] **CI: run `validate_policies.py` and `test_wirename_resolution.py` in a workflow**
  Both are checked in but only run locally. Add a `policy-tests` job
  to `ingest-on-merge.yml` (or a new `tests.yml`) that runs after
  ingest so canonical_map drift breaks the build.
## P2 — polish

_All P2 items complete in this session. Track new polish items here as
they surface._

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

- [ ] **Quantitative precision/recall — grow the labeled set**
  Scaffold complete: `apps/dup-resolver/tests/labeled_pairs.yaml` (26
  pairs from the two demo specs), `apps/dup-resolver/eval_threshold.py`
  (sweep + `--compare` A/B over 5 fingerprint variants), report at
  `docs/eval/precision-recall.md`. Open until the labeled set reaches
  30–50 pairs drawn from real-world (outside-the-repo) MCP servers.
  At that point, re-evaluate whether to adopt the `combined` variant
  in production `fingerprint.py` (current best on the stress set:
  margin −0.028 vs baseline −0.076).
