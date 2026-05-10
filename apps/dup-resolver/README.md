# Dup-Resolver — Layer 2 (L2)

The **brain** of MCP Tool Governance: ingests tool descriptors from APIM-MCP servers, embeds them, clusters near-duplicates, deterministically elects a canonical, and writes the canonical_map that L3 reads at runtime.

> **Scope:** PoC implementation. See [docs/ARCHITECTURE.md §14](../../docs/ARCHITECTURE.md#14-layer-2--api-center--dup-resolver-service) for the full design.

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

- **Per-operation row:** `verdict` (DUPLICATE / WARN / OK / INFO),
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
| `AOAI_ENDPOINT` | `https://common-open-ai.openai.azure.com/` |
| `AOAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` |
| `SEARCH_ENDPOINT` | `https://ai102srch193837986.search.windows.net` |
| `SEARCH_INDEX` | `mcp-tool-fingerprints` |
| `APIM_GATEWAY_BASE` | `https://apimopenai99.azure-api.net` |
| `APIM_KEY_FILE` | `/tmp/apim-master-key.txt` |
| `MCP_SERVERS` | `governed-mcp,messy-mcp` |
| `MCP_SOURCE` | `apim` (default) or `openapi` (read specs from `apim/openapi/*.json`) |
| `OPENAPI_SPEC_DIR` | `apim/openapi` (used when `MCP_SOURCE=openapi`) |
| `CLUSTER_THRESHOLD` | `0.88` default; see *Threshold tuning* below |

Auth uses `DefaultAzureCredential` for both AOAI and AI Search — `az login` is enough locally.

### Threshold tuning — the `CLUSTER_THRESHOLD` knob

The cosine-similarity score above which two tools are considered **duplicates** rather than merely related. Affects:
- the L2 CI gate (`similarity-check.yml`) — `>= threshold` fails the PR
- the WARN band (`threshold − 0.05 ≤ score < threshold`) — flagged for reviewer
- single-linkage clustering inside `cluster.py` — same threshold

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
eastus) and AI Search (`ai102srch193837986`). Use these as triage
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
