# Tools CLI

Operational utilities for the MCP Tool Governance PoC. Currently a thin
collection of scripts; will grow into a proper CLI (registry validation,
canonical_map sync, eval kickoff) during PoC week 1.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `seed_canonical_map.py`

Seeds canonical_map documents into Cosmos `cosmoslab82658` →
`governance/mcp-canonical-map`. Authenticates with `DefaultAzureCredential`
(uses your `az login`), so the runtime APIM MI path is not exercised.

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
