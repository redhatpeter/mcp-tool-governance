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

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | liveness + index doc count |
| `POST` | `/ingest` | re-ingest from APIM tools/list (governed + messy) |
| `POST` | `/similarity` | one-shot: embed body, return top-N nearest existing tools + cluster verdict |
| `GET` | `/clusters` | dump current clusters (for the demo UI) |

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

Auth uses `DefaultAzureCredential` for both AOAI and AI Search — `az login` is enough locally.

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
# 1. Ingest current tool surfaces
curl -X POST http://localhost:8089/ingest

# 2. Inspect clusters
curl -s http://localhost:8089/clusters | jq

# 3. L1 CI similarity check — pretend a PR adds another get-quote tool
curl -X POST http://localhost:8089/similarity \
  -H 'Content-Type: application/json' \
  -d '{"name":"financeQuoteFetch","description":"Fetch a real-time stock quote","domain":"finance"}'
# → {"verdict":"DUPLICATE", "cluster_id":"clu_3", "nearest":[{"id":"governed/financeQuoteGet","score":0.94}, ...]}
```

The CI workflow at `.github/workflows/validate-mcp-tools.yml` calls `/similarity` for every new operation in a PR and fails the build on `DUPLICATE`.
