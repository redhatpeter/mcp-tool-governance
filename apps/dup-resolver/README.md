# Dup-Resolver — Layer 2 (L2)

The **brain** of MCP Tool Governance: ingests tool descriptors from APIM-MCP servers, embeds them, clusters near-duplicates, deterministically elects a canonical, and writes the canonical_map that L3 reads at runtime.

> **Scope:** PoC implementation.

---

## What it does

```
APIM tools/list  ─┐
                  ├─► [fingerprint] ─► [embed] ─► [AI Search upsert] ─► [cluster] ─► [elect canonical] ─► [Cosmos canonical_map]
                  ┘                                                                                              │
                                                                                                                 ▼
                                                                                              L3 APIM policy reads at runtime
```

| Stage | Module |
|---|---|
| Build canonical text from name + summary + params | `fingerprint.py` |
| Call AOAI `text-embedding-3-large` (3072 dims) | `embed.py` |
| Upsert / vector-query AI Search index `mcp-tool-fingerprints` | `search_client.py` |
| Single-linkage clustering at cosine ≥ 0.88 | `cluster.py` |
| Deterministic weighted-score election (no LLM judge) | `elect.py` |

Run as **library** (called by `python -m dup_resolver.ingest`) and as **thin FastAPI** for the demo (`/similarity` so L1 CI can post a PR-changed tool and get a cluster verdict).

---

## How it's used

Two entry points:

1. **CI gate (the one that matters):** [`check_pr.py`](check_pr.py) runs in
   [`similarity-check.yml`](../../.github/workflows/similarity-check.yml) on
   every PR that touches `apim/openapi/*.json`. It diffs the spec against
   `main`, embeds each new/changed operation, vector-queries
   `mcp-tool-fingerprints`, and posts a markdown verdict back to the PR.
   No service is required at PR time — the script talks to AOAI + AI Search
   directly with `DefaultAzureCredential` (or keys, in CI).
2. **Demo HTTP service (`main.py`):** an optional FastAPI surface used
   by the customer demo (Act 4) for the `/clusters` view. Not on the
   critical path; the demo falls back to captured samples if it's down.

### `check_pr.py` — what the verdict contains

- **Per-operation row:** `verdict` (DUPLICATE / WARN / REVIEW / OK / INFO),
  top-match score, top-match server + tool name, threshold in effect.
- **Rename detection** *(INFO row, exit 0):* if the top-match's tool name
  is also being **deleted** in the same PR (computed by diffing the
  base ref's spec against HEAD), the verdict is downgraded from DUPLICATE
  to `ℹ️ INFO — looks like a rename, not a duplicate`. The required check
  still passes so legitimate renames don't block merges.
- **Index freshness footer:** the markdown report ends with
  `Index freshness: oldest top-hit last_seen_utc = ...` so reviewers can
  see at a glance whether the index is stale. If yes, re-run
  `ingest-on-merge.yml` (workflow_dispatch).

### Demo service endpoints (`main.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | liveness + index doc count |
| `POST` | `/ingest` | re-ingest from APIM tools/list (governed + messy) |
| `POST` | `/similarity` | one-shot: embed body, return top-N nearest existing tools + cluster verdict |
| `GET` | `/clusters` | dump current clusters (for the demo UI) |

## Index hygiene — `ingest-on-merge` (Option A reconciliation)

On every push to `main`, [`ingest-on-merge.yml`](../../.github/workflows/ingest-on-merge.yml)
runs `python -m dup_resolver.ingest` against the freshly merged specs:

1. Embed every operation from `apim/openapi/*.json`.
2. Upsert into `mcp-tool-fingerprints` with `last_seen_utc = <now>`.
3. **Reconcile:** compute `index_keys − authored_keys` and
   `delete_documents()` the difference, so renamed/deleted operations
   don't leave ghost duplicates that L2 would later flag against new PRs.

The first live run dropped 8 stale camelCase ghost docs from `messy-mcp`.
Log summary fields: `tools`, `indexed`, `stale_ids`, `deleted_stale`.

---

## Setup

```bash
cd apps/dup-resolver
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in endpoints/keys (RBAC preferred — see below)
```

### Required env

| Var | Example |
|---|---|
| `AOAI_ENDPOINT` | `https://common-open-ai2.openai.azure.com/` |
| `AOAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` |
| `SEARCH_ENDPOINT` | `https://ai102srch193837986-mig.search.windows.net` |
| `SEARCH_INDEX` | `mcp-tool-fingerprints` |
| `APIM_GATEWAY_BASE` | `https://apimopenai992.azure-api.net` |
| `APIM_KEY_FILE` | `/tmp/apim-master-key.txt` |
| `MCP_SERVERS` | `governed-mcp,messy-mcp` |
| `MCP_SOURCE` | `apim` (default) or `openapi` (read specs from `apim/openapi/*.json`). **Use `openapi` once L3 is deployed:** the gateway's `tools/list` filter hides duplicates using the same canonical map ingest writes, so a gateway-sourced ingest sees a shrinking catalog. |
| `OPENAPI_SPEC_DIR` | `apim/openapi` (used when `MCP_SOURCE=openapi`) |
| `CLUSTER_THRESHOLD` | `0.88` default; see *Threshold tuning* below |
| `REVIEW_THRESHOLD` | `0.65` default; soft "reviewer should look at this" tier — see *Threshold tuning* |

Auth uses `DefaultAzureCredential` for both AOAI and AI Search — `az login` is enough locally.

### Threshold tuning — the `CLUSTER_THRESHOLD` knob

The cosine-similarity score above which two tools are considered **duplicates** rather than merely related. Affects:
- the L2 CI gate (`similarity-check.yml`) — `>= threshold` fails the PR
- the WARN band (`threshold − 0.05 ≤ score < threshold`) — flagged for reviewer
- the **REVIEW** band (`REVIEW_THRESHOLD ≤ score < threshold − 0.05`) — surfaced in the PR comment but does not fail the check (added 2026-05-10 from the precision/recall study; catches real-world cross-vendor semantic duplicates such as `github.create_issue` vs `linear.createIssue` at 0.651)
- single-linkage clustering inside `cluster.py` — uses `CLUSTER_THRESHOLD` only

| Value | Behavior | When to use |
|---|---|---|
| `0.85` | Aggressive — catches paraphrases, more false positives | New environment with no labeled data; tune down later |
| **`0.88`** | **Ship default** — caught every duplicate in our test suite without false positives | Most repos |
| `0.92` | Tightened — only near-verbatim duplicates hard-fail; paraphrases get WARN instead | Production orgs that prefer reviewer gates over auto-blocks |
| `0.95+` | Permissive — only catches obvious copy-paste | Probably too loose; not recommended |

**How to override per-repo without a code change:** set the GitHub repo variable `CLUSTER_THRESHOLD` (Settings → Secrets and variables → Actions → Variables). The `similarity-check` workflow reads it via `${{ vars.CLUSTER_THRESHOLD }}` and exports it as an env var; `config.py` picks it up. Falls back to `0.88` from `config.py` if unset.

This repo currently overrides to **`0.92`** — see `gh variable list` to confirm.

Validate any threshold choice locally:
```bash
cd apps/dup-resolver && source .venv/bin/activate
CLUSTER_THRESHOLD=0.92 bash tests/run_scenarios.sh
```

### Provision the index (one-time)

```bash
python -m dup_resolver.provision_index
```

### Run the service

```bash
uvicorn main:app --host 0.0.0.0 --port 8089
```

(Port 8089 is intentional — finance-fakes occupies 8088.)

---

## Demo flow (Act 4 — adds to the existing 3-act demo)

```bash
# 1. Ingest current tool surfaces (or just rely on ingest-on-merge having run)
curl -X POST http://localhost:8089/ingest

# 2. Inspect clusters
curl -s http://localhost:8089/clusters | jq

# 3. L2 CI similarity check — pretend a PR adds another get-quote tool
curl -X POST http://localhost:8089/similarity \
  -H 'Content-Type: application/json' \
  -d '{"name":"financeQuoteFetch","description":"Fetch a real-time stock quote","domain":"finance"}'
# → {"verdict":"DUPLICATE", "cluster_id":"clu_3", "nearest":[{"id":"governed/financeQuoteGet","score":0.958}, ...]}
```

The **CI gate** at [`.github/workflows/similarity-check.yml`](../../.github/workflows/similarity-check.yml)
runs `check_pr.py` (not the HTTP service) for every changed operation in a
PR and fails the build on `DUPLICATE`. PR #1 in this repo has the captured
live run (`DUPLICATE 0.958` at threshold `0.92`).

## Local test suite

```bash
cd apps/dup-resolver && source .venv/bin/activate
bash tests/run_scenarios.sh        # 9/9 scenarios at threshold 0.88
CLUSTER_THRESHOLD=0.92 bash tests/run_scenarios.sh   # repo-default sweep
```

Scenarios cover: clean-no-change, novel-op (OK), exact-rename (DUPLICATE),
strong-paraphrase (DUPLICATE), weak-paraphrase (WARN), cross-server
(threshold-tolerant), malformed-JSON (exit 2), rename-detected (INFO,
exit 0), and multi-file-pr (two specs in one PR).

## Performance budget — what "normal" looks like

Numbers below are from a warm AOAI deployment (`text-embedding-3-large`,
eastus) and AI Search (`ai102srch193837986-mig`). Use these as triage
anchors: a 5× regression on any line is worth investigating before
chalking it up to network jitter.

### Local — `check_pr.py` cold (Python interpreter freshly invoked)

| Operations scored | Wall clock | Notes |
|---|---|---|
| 1 | ~6.7s | Dominated by AOAI handshake + first embed call |
| 5 | ~7.6s | Embed batching amortizes the AOAI cost |
| 20 | ~12.1s | Linear in op count once the connection is warm |

Source: `LATENCY BUDGET` block emitted by `tests/run_scenarios.sh`.

### CI — end-to-end workflow time

| Workflow | Typical | Cold-cache outliers |
|---|---|---|
| `validate-mcp-tools` (L1 lint, stdlib only) | ~25s | ~40s |
| `similarity-check` (L2 PR gate) | ~60–90s | ~120s |
| `ingest-on-merge` (Option A reconciliation) | ~50–70s | ~100s |
| `daily-ingest` (nightly cron) | ~50–70s | same |

Breakdown of a typical `similarity-check` run:

| Phase | ~Time | Notes |
|---|---|---|
| Runner spin-up | 10–15s | Out of our control |
| Checkout + Python setup | 5–10s | Cached on most runners |
| `pip install -r requirements.txt` | 20–30s | Largest single phase |
| `check_pr.py` (1–5 ops) | 7–10s | The actual gate |
| Markdown summary post | <1s | |

**When to investigate:** any `similarity-check` run > 5 minutes, any
`ingest-on-merge` run > 4 minutes, or `check_pr.py` local runs that
take more than 30s for a single op. Most often the cause is AOAI
throttling (HTTP 429) or AI Search 5xx — both surface in the workflow
log under the relevant step.

## Index hygiene — two-tier reconciliation

The index can drift between merges (failed ingest run, manual portal
edits, schema migrations). We defend with two workflows + one PR-time
signal:

| Layer | What | When |
|---|---|---|
| 1. `ingest-on-merge.yml` | Re-embed + delete stale docs on every push to `main` | Per-merge, low-latency |
| 2. `daily-ingest.yml` | Same logic, scheduled at 04:17 UTC | Daily backstop |
| 3. Stale-index alert in `check_pr.py` | Bold ⚠️ banner in the PR verdict if oldest top-hit `last_seen_utc` > 24h | At PR time |

Layers 1+2 keep the index fresh; layer 3 lets reviewers know if both
have failed and they shouldn't trust the score until someone re-runs
`workflow_dispatch` on either.

## Adding a new MCP server (spec-source manifest)

The mapping from OpenAPI filename stem to APIM MCP server name lives in
[`apim/openapi/_servers.yaml`](../../apim/openapi/_servers.yaml). Add a
new server in two steps — no code changes:

1. Drop the OpenAPI spec at `apim/openapi/<stem>.json` (must lint clean
   under `tools-cli/lint.py`).
2. Add one line under `servers:` in `_servers.yaml`:
   ```yaml
   servers:
     finance-governed: governed-mcp
     finance-messy:    messy-mcp
     hr-governed:      hr-mcp        # ← new
   ```

The next push to `main` triggers `ingest-on-merge` which embeds the new
server's tools and reconciles the index. Stems that aren't listed in the
manifest are intentionally **skipped** (not auto-discovered) so renaming
a file doesn't silently change the indexed corpus.

If the manifest is missing or PyYAML is unavailable (e.g. early-stage
tests), the loader falls back to a built-in default that matches this
repo's two stems. Production deployments should always author the file.

## Threshold tuning — precision/recall study

The 0.92 threshold (`CLUSTER_THRESHOLD` repo variable) is defended by a
labeled pair set at [`tests/labeled_pairs.yaml`](tests/labeled_pairs.yaml)
and an evaluator that sweeps thresholds and reports precision / recall /
F1 for the **duplicate** class:

```bash
cd apps/dup-resolver && source .venv/bin/activate
python3 eval_threshold.py                                            # console
python3 eval_threshold.py --markdown precision-recall.md
python3 eval_threshold.py --thresholds 0.85,0.88,0.90,0.92,0.95
python3 eval_threshold.py --compare                                  # A/B all variants
python3 eval_threshold.py --variant synonyms                         # single non-default
```

The current pair set has **76 hand-curated pairs** (33 duplicates, 43
novels) — 26 from the two demo specs plus 50 real-world pairs sourced
from canonical `modelcontextprotocol/servers` reference repos and widely-
used third-party MCP servers (linear, jira, notion, confluence, slack,
discord, dropbox, gdrive, postgres, mysql, sqlite, redis, memcached,
aws-s3, gcs, kubernetes, helm, docker, sentry, rollbar, stripe, square,
playwright, puppeteer, fetch, brave-search, memory, github, gitlab).
Intentionally **stress-loaded** with hard cases: syntactic/semantic/
cross-server/cross-vendor duplicates plus hard negatives like "same
domain different entity" and "same entity different action".
**Headline:** precision **1.000** at the production
threshold 0.92 (0 false positives over 43 novels) — the hard block is
robust. Recall at 0.92 is 0.091; the REVIEW band at 0.65 (shipped 2026-
05-10) recovers ~64 % of duplicates as soft "reviewer should look" PR
surfaces. Grow the labeled set whenever a real PR exposes a new failure
mode.

### Fingerprint variants (offline A/B)

`eval_threshold.py --compare` runs the same labeled set through five
fingerprint shapes (defined inline in the eval script — production
`fingerprint.py` is **not** touched). Variants:

| Variant             | What changes                                                         |
|---------------------|----------------------------------------------------------------------|
| `baseline`          | Production shape (control)                                           |
| `no-domain`         | Drop the `domain:` line (test whether shared domain inflates novels) |
| `synonyms`          | Map find/search/lookup→search, get/fetch/read→get, etc. in action+description |
| `description-heavy` | Repeat the description as a second `intent:` line (semantic weight)  |
| `combined`          | no-domain + synonyms + description-heavy stacked                     |

Latest run on the **76-pair set** (2026-05-10) ranked variants by
separability margin (less negative = better): `description-heavy` (−0.215)
> `baseline` (−0.264) > `synonyms` (−0.286) > `combined` (−0.312) >
`no-domain` (−0.359). The variant ranking **flipped** when the set grew
from 26 → 76 pairs and added vendor diversity (linear/jira/notion/etc.):
`combined` was the leader at 26 pairs but now has the worst margin
because same-domain prose lifts novel scores faster than true-duplicate
scores. **Production fingerprint stays at `baseline`.** The two-tier
verdict (DUPLICATE ≥ 0.92 hard block, REVIEW ≥ 0.65 soft surface) is the
architectural fix for the embedding ceiling.
Grow further only if a customer-specific corpus changes the picture.

## Canonical map — L2 → L3 handoff

After clustering and electing a canonical per cluster, ingest writes one
document per cluster to a Cosmos SQL container so L3 (runtime APIM
policy, future) can point-read the decision without re-running L2.

**Container:** `governance.mcp-canonical-map` on `cosmoslab826582`,
partitioned by `/canonical_id`.

**Schema (one doc per cluster):**

```jsonc
{
  "id":              "<canonical_id>",   // == server__name
  "canonical_id":    "<canonical_id>",   // == partition key
  "cluster_id":      "<cluster_id>",
  "canonical_server":"governed-mcp",
  "canonical_name":  "financeCustomerCreate",
  "score":           1.0,
  "score_breakdown": { "governed":0.30, "name":0.10, ... },
  "members": [
    { "id":"<doc_id>", "server":"...", "name":"...", "is_canonical":true|false }
  ],
  "members_count":    3,
  "last_updated_utc": "2026-05-10T...Z",
  "ingest_run_id":    "<GITHUB_SHA or uuid>"
}
```

**Wiring:**

```bash
# .env (or export)
COSMOS_ENDPOINT=https://cosmoslab826582.documents.azure.com:443/
COSMOS_DATABASE=governance
COSMOS_CONTAINER=mcp-canonical-map
# Auth precedence — first match wins:
#   COSMOS_KEY     env var (master key)         [if local auth allowed]
#   COSMOS_KEY_FILE path to file w/ master key  [if local auth allowed]
#   DefaultAzureCredential                       [requires AAD data-plane RBAC]
```

`cosmoslab826582` has **local auth disabled by Azure Policy**, so
production / CI will use the AAD path. The principal needs `Cosmos DB
Built-in Data Contributor` (`00000000-0000-0000-0000-000000000002`) at
account scope or tighter:

```bash
PRINCIPAL=$(az ad signed-in-user show --query id -o tsv)
az cosmosdb sql role assignment create -a cosmoslab826582 -g cosmos-ws \
  --role-definition-id 00000000-0000-0000-0000-000000000002 \
  --principal-id "$PRINCIPAL" \
  --scope "/"
```

**Disabling the writer:** leave `COSMOS_ENDPOINT` empty. The rest of
ingest still runs; you'll see a one-time `[canonical_map] disabled`
log line on stderr. Useful for local dev without Cosmos.

**Reconcile:** mirrors the AI Search ghost-doc cleanup. After the
upsert pass, anything in Cosmos whose `canonical_id` isn't in the
just-written set is deleted — keeps the map in lock-step with the
clusters L2 actually elected this run.

**Reading from L3 (preview):**

```python
import canonical_map
doc = canonical_map.read_canonical("governed-mcp__financeCustomerCreate")
# doc["members"] is the list of duplicates, with one is_canonical=True.
```

**Validating writer ↔ policy schema agreement:**

After any change to `canonical_map.py` or to `apim/policies/*.xml`,
replay the exact Cosmos queries the policies issue and assert the
expected canonical / drop-set behavior:

```bash
cd apps/dup-resolver && source .venv/bin/activate
export COSMOS_ENDPOINT=https://cosmoslab826582.documents.azure.com:443/
python3 ingest.py >/dev/null   # populate the map
python3 tests/validate_policies.py
```

The validator probes the demo data (`messy-mcp` `createCustomer` /
`Create_Customer` / `customer_create` cluster + `invoice_create_v1` / `v2`)
and would have caught any of the schema mismatches the round-trip
tests are likely to surface in production. Exit code: `0` ok, `1`
schema disagreement, `2` Cosmos unreachable / map empty.

