# Tools CLI

Operational utilities for the MCP Tool Governance PoC. Currently a thin
collection of scripts; the L1 lint (`lint.py`) is the load-bearing piece
and runs in the
[`validate-mcp-tools.yml`](../.github/workflows/validate-mcp-tools.yml)
CI gate. The seed script below is for one-time bootstrap of an empty
`mcp-canonical-map` container (production writes come from
[`apps/dup-resolver/canonical_map.py`](../apps/dup-resolver/canonical_map.py)
on every push to `main`).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running the demo locally

The seed script and the full stack expect three Azure resources to already
exist: **Azure AI Search**, **Cosmos DB**, and **API Management** (plus an
Azure OpenAI embeddings deployment). This section walks through provisioning
them once and then bringing the whole stack up the same way it runs today.

### 0. Prerequisites

- **Azure CLI** logged in to the subscription that hosts the resources:
  ```bash
  az login
  az account set --subscription <your-subscription-id>
  ```
  All scripts authenticate with `DefaultAzureCredential` (your `az login`) —
  no keys are required when the services have RBAC data-plane access enabled.
- **Python 3.10+** with a venv per app (`tools-cli`, `apps/dup-resolver`,
  `apps/finance-fakes`, `frontend`).
- **ngrok** on `PATH` (`snap install ngrok`) — used by `start-all.sh` to
  expose the local finance backend to APIM.

### 1. Configure endpoints (`.env`)

The dup-resolver reads all endpoints from `apps/dup-resolver/.env`. Copy the
example and fill in your resource names:

```bash
cd apps/dup-resolver
cp .env.example .env
```

| Var | What it points at | Example |
|---|---|---|
| `AOAI_ENDPOINT` | Azure OpenAI account (embeddings) | `https://<aoai>.openai.azure.com/` |
| `AOAI_EMBEDDING_DEPLOYMENT` | embeddings deployment name | `text-embedding-3-large` |
| `SEARCH_ENDPOINT` | Azure AI Search service | `https://<search>.search.windows.net` |
| `SEARCH_INDEX` | vector index name | `mcp-tool-fingerprints` |
| `APIM_GATEWAY_BASE` | APIM gateway URL | `https://<apim>.azure-api.net` |
| `MCP_SERVERS` | MCP APIs on APIM | `governed-mcp,messy-mcp` |
| `COSMOS_ENDPOINT` | Cosmos account (L2→L3 handoff) | `https://<cosmos>.documents.azure.com:443/` |

The seed script (`tools-cli/seed_canonical_map.py`) reads `COSMOS_ACCOUNT_URL`,
`COSMOS_DATABASE`, and `COSMOS_CONTAINER` from the environment, defaulting to
the demo Cosmos account / `governance` / `mcp-canonical-map`. Override them if
your account name differs.

### 2. Provision Azure AI Search

Creates the `mcp-tool-fingerprints` vector index (3072-dim embeddings). The
script is idempotent — safe to re-run.

```bash
cd apps/dup-resolver
source .venv/bin/activate            # pip install -r requirements.txt first
python provision_index.py            # create if missing
# python provision_index.py --recreate   # drop and recreate (data loss)
```

Populate the index by running an ingest pass (`python -m dup_resolver.ingest`)
or by merging a PR that touches `apim/openapi/*.json` — the
[`ingest-on-merge.yml`](../.github/workflows/ingest-on-merge.yml) workflow
embeds every operation and upserts it.

### 3. Provision + seed Cosmos DB

[`scripts/ensure-cosmos.sh`](../scripts/ensure-cosmos.sh) makes the governed
Cosmos account reachable (handles the org "disable public network access"
policy via the `SecurityControl=Ignore` exclusion tag, then allowlists your
machine + APIM egress) and seeds the `canonical_map` so L2 similarity and L3
alias rewrite work. It calls `tools-cli/seed_canonical_map.py` under the hood.

```bash
# From repo root:
./scripts/ensure-cosmos.sh              # ensure network + seed
# ./scripts/ensure-cosmos.sh --no-seed  # network only
```

To seed manually (network already correct):

```bash
# From repo root, with the tools-cli venv activated:
python tools-cli/seed_canonical_map.py
```

### 4. Deploy the APIM L3 policies

[`apim/deploy/deploy_l3_policies.py`](../apim/deploy/deploy_l3_policies.py)
builds the canonical-rewrite + tools-list-filter policies per server and PUTs
them onto the `governed-mcp` and `messy-mcp` APIs. The caller needs APIM
contributor on the target service.

```bash
az login   # needs APIM contributor
python3 apim/deploy/deploy_l3_policies.py
```

> Edit `SUBSCRIPTION_ID`, `RESOURCE_GROUP`, and `APIM_NAME` at the top of the
> script if your APIM instance differs from the demo defaults.

### 5. Bring up the full stack

[`scripts/start-all.sh`](../scripts/start-all.sh) is the push-button runner. It
is idempotent (kills prior instances first) and does the following:

1. Ensures Cosmos is reachable + seeded (calls `ensure-cosmos.sh`).
2. Starts the finance-fakes FastAPI backend on `127.0.0.1:8010`.
3. Opens an ngrok tunnel and points both APIM finance APIs at it.
4. Starts the dup-resolver FastAPI on `127.0.0.1:8089`.
5. Starts the Streamlit frontend on `127.0.0.1:8501`.

```bash
# From repo root:
./scripts/start-all.sh                 # bring everything up
# ./scripts/start-all.sh --no-apim     # skip the APIM service-url update
# ./scripts/start-all.sh --no-cosmos   # skip the Cosmos ensure/seed step
```

When it finishes you'll have:

| Service | URL |
|---|---|
| UI (Streamlit) | http://localhost:8501 |
| Resolver health | http://127.0.0.1:8089/healthz |
| Backend docs | http://127.0.0.1:8010/docs |
| ngrok tunnel | value printed + written to `.ngrok-url` |

Stop everything with [`scripts/stop-all.sh`](../scripts/stop-all.sh).

---

## Scripts

### `seed_canonical_map.py`

Seeds canonical_map documents into Cosmos `governance/mcp-canonical-map`.
Authenticates with `DefaultAzureCredential` (uses your `az login`), so the
runtime APIM MI path is not exercised. Called automatically by
[`scripts/ensure-cosmos.sh`](../scripts/ensure-cosmos.sh); run it directly for
a manual re-seed.

```bash
# From repo root, with venv activated:
python tools-cli/seed_canonical_map.py
```

Seeds two demo docs by default:

| Doc id | Role | `primary.name` |
|---|---|---|
| `get_customer` | alias | `crm_customer_get` |
| `crm_customer_get` | canonical (self-referential) | `crm_customer_get` |

The alias doc exercises the rewrite branch in the policy; the canonical doc
exercises the no-op branch (`id == primary.name`). Edit the `SEEDS` list in
the script to add more.

### Document shape (must match policy assumption)

```json
{
  "id": "get_customer",
  "canonical_id": "get_customer",
  "primary": {
    "name": "crm_customer_get",
    "domain": "crm",
    "entity": "customer",
    "action": "get"
  },
  "aliases": ["get_customer", "fetch_customer"],
  "election": { "method": "seed", "at": "2026-05-08T00:00:00Z" }
}
```

`canonical_id` is the partition-key field (`/canonical_id`); for the simple
direct-lookup pattern the policy uses, `canonical_id == id` for every doc so
that lookups by `id` find the right partition.
