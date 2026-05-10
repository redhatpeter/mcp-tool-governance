# APIM Policies

Versioned APIM policy artifacts. The source of truth for the design behind each
policy is [docs/ARCHITECTURE.md §15](../../docs/ARCHITECTURE.md). This directory
holds the deployable form so it can be diffed, reviewed, and (eventually)
deployed via APIM Policy Fragments + Terraform.

## Files

| File | Scope | Purpose |
|---|---|---|
| [canonical-rewrite.policy.xml](canonical-rewrite.policy.xml) | MCP server (per imported API) | JWT validation, rate limiting, and canonical-name rewrite for `tools/call` JSON-RPC frames. Fails open on Cosmos errors. |
| [tools-list-filter.policy.xml](tools-list-filter.policy.xml) | MCP server (per imported API) | Outbound filter for `tools/list` responses. Drops every tool whose fully-qualified id (`<server>__<name>`) appears in any cluster's `aliases` array. The LLM only ever sees canonicals. Fails open. |

## Where it attaches

Azure Portal → **APIs → MCP Servers → \<server\> → MCP → Policies**.
Replaces the default empty `<inbound>` block. Apply per MCP server (e.g. once
on `governed/mcp`, once on each `<domain>-raw/mcp`, etc.).

## Prerequisites

The policy assumes the following are configured on the APIM instance hosting
the MCP server. PoC pairing:

- **APIM:** `apimopenai99` (RG `Default-ActivityLogAlerts`, eastus)
- **Cosmos:** `cosmoslab82658` (RG `cosmos-ws`, westus) — DB `governance`, container `mcp-canonical-map` (PK `/canonical_id`, 400 RU/s)

> **Status (2026-05-08):** Pairing is **DONE**. APIM system-assigned MI
> `29569271-d247-4907-a841-feb848f4016f` holds **Cosmos DB Built-in Data
> Reader** scoped to `/dbs/governance/colls/mcp-canonical-map`. The DB and
> container exist and are empty — seed canonical_map docs before smoke testing.

The commands below are kept for reference / re-deploy in another environment.

### 1. APIM system-assigned managed identity

```bash
APIM_NAME=apimopenai99
APIM_RG=Default-ActivityLogAlerts

az apim update -n "$APIM_NAME" -g "$APIM_RG" --set identity.type=SystemAssigned
APIM_MI=$(az apim show -n "$APIM_NAME" -g "$APIM_RG" --query identity.principalId -o tsv)
echo "APIM MI: $APIM_MI"
```

### 2. Cosmos database, container, and data-plane role assignment

```bash
COSMOS_ACCOUNT=cosmoslab82658
COSMOS_RG=cosmos-ws

# DB + container (PK /canonical_id, 400 RU/s shared throughput)
az cosmosdb sql database create \
  --account-name "$COSMOS_ACCOUNT" -g "$COSMOS_RG" \
  --name governance --throughput 400

az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" -g "$COSMOS_RG" \
  --database-name governance \
  --name mcp-canonical-map \
  --partition-key-path /canonical_id

# Built-in Cosmos DB Data Reader (00000000-0000-0000-0000-000000000001)
az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" -g "$COSMOS_RG" \
  --scope "/dbs/governance/colls/mcp-canonical-map" \
  --principal-id "$APIM_MI" \
  --role-definition-id 00000000-0000-0000-0000-000000000001
```

No keys, no Key Vault entries. See [ADR 0001](../../docs/adr/0001-apim-mcp-native.md).

### 3. Placeholders in the policy XML

Before pasting into the Portal, replace these literal placeholders:

| Placeholder | Replace with | Notes |
|---|---|---|
| `<tenant-id>` | Your Entra tenant GUID | Used in the OpenID metadata URL. |
| `api://mcp-gateway` | Your registered API audience | The `aud` claim required on inbound JWTs. |
| `cosmoslab82658.documents.azure.com` | Cosmos account hostname | Already set to the PoC pairing target. Change if you point at a different Cosmos account. |

For a production-grade flow these become **APIM Named Values** (or Key Vault
references) and the policy uses `{{tenant-id}}` etc. — see ARCHITECTURE §24
#10 (Policy Fragments).

## Cosmos document shape (assumed by the policies)

L2 (`apps/dup-resolver/canonical_map.py`) writes one document per cluster.
The shape is unified — both policies read from the same docs, just
different fields:

```jsonc
{
  "id":              "<server>__<canonical_name>",   // partition key value
  "canonical_id":    "<server>__<canonical_name>",
  "cluster_id":      "<cluster_id>",
  "canonical_server":"governed-mcp",
  "canonical_name":  "financeCustomerCreate",
  "primary": {                                        // tools/call rewrite reads here
    "id":     "<server>__<canonical_name>",
    "server": "governed-mcp",
    "name":   "financeCustomerCreate"
  },
  "aliases": [                                        // tools/list filter reads here
    "messy-mcp__createCustomer",
    "messy-mcp__Create_Customer"
  ],
  "members": [
    { "id":"...", "server":"...", "name":"...", "is_canonical": true|false }
  ],
  "members_count":    3,
  "score":            1.0,
  "score_breakdown":  { ... },
  "last_updated_utc": "2026-05-10T...Z",
  "ingest_run_id":    "<GITHUB_SHA or uuid>"
}
```

| Field | Read by |
|-------|---------|
| `primary.name`             | `canonical-rewrite.policy.xml` (rewrites `params.name` on `tools/call`) |
| `aliases[]`                | `tools-list-filter.policy.xml` (drops matching tools from `tools/list`) |
| `score` / `score_breakdown`| Debug / App Insights workbooks (not read by policies) |

If `id == primary.name` (singleton cluster — no duplicates) both policies
are no-ops for that doc. See ARCHITECTURE §13–§14 for the full
canonical_map design.

> **Note on the `tools/call` rewrite (L3 step 3):** the policy now
> synthesizes the fully-qualified id as `<server-name>__<wire_name>`
> (matching the writer's `doc_id` format) before lookup. The Cosmos
> query joins on `c.id = @id OR ARRAY_CONTAINS(c.aliases, @id)`, so a
> requested alias resolves to the canonical wire name in one call.
> Validated end-to-end via
> `apps/dup-resolver/tests/validate_policies.py` (replays the same SQL
> and asserts expected behavior on the demo data).

## Failure mode

**Fail-open** for both policies. Any Cosmos error or missing document
results in the original request/response passing through unchanged:

- `canonical-rewrite.policy.xml` — `send-request` uses `ignore-error="true"`
  and the value-set guard returns the originally-requested tool name on
  any Cosmos error or missing document. To switch to fail-closed, set
  `ignore-error="false"` and remove the null guard.
- `tools-list-filter.policy.xml` — same pattern; an empty / errored
  Cosmos response yields an empty drop set, so every tool passes through.

The trade-off: a transient Cosmos blip will not break the MCP gateway,
but it will momentarily expose non-canonical members. App Insights
should alert on a sustained absence of `x-mcp-tools-filtered` headers
once L3 is in production.

## Testing

There is no automated test for either policy yet. Manual smoke tests:

### `canonical-rewrite.policy.xml` (tools/call)

1. Insert a doc with `id="foo_bar"` and `primary.name="canonical_foo"` into
   `mcp-canonical-map`.
2. Issue an MCP `tools/call` with `params.name="foo_bar"` against the MCP
   server endpoint.
3. Confirm:
   - Backend receives `params.name="canonical_foo"`.
   - Response carries `x-mcp-canonical-rewrite: foo_bar -> canonical_foo`.
   - App Insights shows the rewrite header in the request trace.
4. Re-issue within 60s; verify cache hit (no Cosmos call in APIM trace).

### `tools-list-filter.policy.xml` (tools/list)

1. Run `apps/dup-resolver` ingest end-to-end against the live MCP servers
   (or use the openapi source). Confirm `mcp-canonical-map` has at least
   one doc with non-empty `aliases`. (The PoC stress data — `messy-mcp`
   `createCustomer` / `Create_Customer` / `customer_create` — produces
   exactly this shape.)
2. Replace `<server-name>` in the policy with the real server name
   (e.g. `messy-mcp`) and attach to the corresponding APIM MCP server.
3. Issue `tools/list` against that server.
4. Confirm:
   - The response no longer contains the alias members (e.g.
     `createCustomer` and `Create_Customer` should be dropped; only
     `customer_create` remains).
   - Response carries `x-mcp-tools-filtered: <count>`.
   - App Insights shows the filter header in the response trace.
5. Re-issue within 60s; verify cache hit.

A scripted version of these will land in `tools-cli/` during PoC week 1.
