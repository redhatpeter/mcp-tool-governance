# APIM Policies

Versioned APIM policy artifacts. This directory
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

No keys, no Key Vault entries. The APIM managed identity is granted access
directly (APIM-MCP native pattern).

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

**Automated:** [`apps/dup-resolver/tests/validate_policies.py`](../../apps/dup-resolver/tests/validate_policies.py)
replays the exact Cosmos SQL each policy issues against the live
`mcp-canonical-map` container and asserts the expected behavior across
8 scenarios (3 alias resolutions, 1 already-canonical, 1 singleton, 1
unknown fail-open, 2 `tools/list` drop-set cases). Wired into the
[`policy-tests.yml`](../../.github/workflows/policy-tests.yml) CI gate;
latest green run
[25637828620](https://github.com/redhatpeter/mcp-tool-governance/actions/runs/25637828620).
A verdict-tier regression test
([`tests/test_verdict_tiers.py`](../../apps/dup-resolver/tests/test_verdict_tiers.py))
locks the DUPLICATE / WARN / REVIEW / OK / INFO band boundaries plus
four real-world cross-vendor REVIEW examples.

**Live deployment status (2026-05-10):** both policies are attached to
`governed-mcp` and `messy-mcp` on `apimopenai99`. Live captures:
`messy-mcp/tools/list` → `x-mcp-tools-filtered: 3`;
`messy-mcp/tools/call createCustomer` → `x-mcp-canonical-rewrite:
createCustomer -> customerCreate`.

**Manual smoke tests** (for re-deploy in a new environment):

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

A scripted version of these lives in
[`apps/dup-resolver/tests/validate_policies.py`](../../apps/dup-resolver/tests/validate_policies.py)
and runs in CI on every change to the policies or the writer.

---

## How the two policies are deployed (merged, not separate)

In the Portal you will see **one policy document per MCP server**, not two.
[`apim/deploy/deploy_l3_policies.py`](../deploy/deploy_l3_policies.py) reads
both source files, strips comments, extracts each one's `<inbound>` and
`<outbound>` bodies, concatenates the two `<outbound>` blocks, substitutes
`{{server-name}}`, and PUTs the result. The merged artifacts live under
[`apim/deploy/_built/`](../deploy/_built/) — diff those against the Portal
to confirm what's deployed.

Why merge? APIM allows only one policy per scope. The two source files are
kept separate in this repo because they solve independent problems
(inbound rewrite vs outbound filter) and are unit-tested independently;
the merge is a packaging step.

---

## End-to-end walkthrough with live data

Worked example using the actual rows in `cosmoslab82658 / governance /
mcp-canonical-map` and the actual operations in
[`apim/openapi/finance-messy.json`](../openapi/finance-messy.json) as of
2026-06-11. Every query in this section is copy-pasteable into the Cosmos
Data Explorer.

### The cluster we'll demo against

```sql
-- Find every cluster with a non-empty aliases[] (the only ones policies do work for)
SELECT c.id, c.aliases, c.canonical_server
FROM c
WHERE ARRAY_LENGTH(c.aliases) > 0
```

Returns two rows on the live PoC instance:

| `id` (canonical) | `aliases[]` | `canonical_server` |
|---|---|---|
| `messy-mcp__customerCreate` | `["messy-mcp__createCustomer"]` | `messy-mcp` |
| `messy-mcp__invoiceCreateV1` | `["messy-mcp__invoiceCreateV2"]` | `messy-mcp` |

The full doc for the customer cluster (abbreviated):

```jsonc
{
  "id": "messy-mcp__customerCreate",
  "canonical_id": "messy-mcp__customerCreate",
  "canonical_server": "messy-mcp",
  "canonical_name": "customerCreate",
  "primary":  { "id": "messy-mcp__customerCreate", "server": "messy-mcp", "name": "customerCreate" },
  "aliases":  [ "messy-mcp__createCustomer" ],
  "members":  [
    { "id": "messy-mcp__createCustomer", "server": "messy-mcp", "name": "createCustomer", "is_canonical": false },
    { "id": "messy-mcp__customerCreate", "server": "messy-mcp", "name": "customerCreate", "is_canonical": true }
  ],
  "score": 0.5,
  "score_breakdown": { "governed": 0, "name": 0.1, "domain": 0.15, "verb": 0.1, "desc": 0.15, "guidance": 0 }
}
```

Every other doc in the container is a singleton (`aliases: []`). The
policies run against those too, but they no-op — there is nothing to drop
and nothing to rewrite.

### The 13 → 12 → 10 funnel on `messy-mcp`

| Stage | Count | Reason |
|---|---|---|
| OpenAPI ops declared | **13** | from `apim/openapi/finance-messy.json` |
| Wire tools surfaced by `tools/list` | **12** | APIM-MCP normalizes `summary` → wire name; `createCustomer` and `Create_Customer` both normalize to `createCustomer` and APIM keeps only the **first declared** (gateway naming-drift failure mode) |
| After L3 outbound filter | **10** | Two aliases dropped: `createCustomer` (alias of `customerCreate`) and `invoiceCreateV2` (alias of `invoiceCreateV1`). Response carries `x-mcp-tools-filtered: 2` |

Governed-mcp has 8 ops → 8 wire tools → 8 after filter (no aliases targeting
governed-mcp in the current data). Each `tools/list` call is per-server; the
agent never sees an aggregate count.

### Flow A — `tools/list` on `messy-mcp` (the filter path)

#### 1. Wire request

```http
POST https://apimopenai99.azure-api.net/messy-mcp/mcp HTTP/1.1
Ocp-Apim-Subscription-Key: <key>
Content-Type: application/json

{ "jsonrpc": "2.0", "id": 1, "method": "tools/list" }
```

#### 2. APIM `<inbound>`

`rpcMethod == "tools/list"` → the rewrite branch's `<when>` is **false**, so
the inbound block is a no-op. Request flows to backend untouched.

#### 3. Backend response (12 wire tools)

```json
{ "jsonrpc":"2.0","id":1,"result":{"tools":[
  {"name":"createCustomer"},      {"name":"customerCreate"},
  {"name":"customerAPIFinalV3"},  {"name":"customerFind"},
  {"name":"customerSearch"},      {"name":"customerLookup"},
  {"name":"invoiceCreateV1"},     {"name":"invoiceCreateV2"},
  {"name":"invoiceCreateLegacy"}, {"name":"lookup"},
  {"name":"create"},              {"name":"list"}
]}}
```

#### 4. APIM `<outbound>` — alias filter

a. `cache-lookup-value key="aliasdrop:messy-mcp"` → cold cache, **miss**.
b. Mint AAD token via `<authentication-managed-identity>`. POST to Cosmos:

```sql
SELECT VALUE c.aliases
FROM c
WHERE c.canonical_server = "messy-mcp"
   OR EXISTS(SELECT VALUE m FROM m IN c.members WHERE m.server = "messy-mcp")
```

c. Cosmos returns:

```json
{ "Documents": [
    [ "messy-mcp__createCustomer" ],
    [ "messy-mcp__invoiceCreateV2" ]
] }
```

d. Flatten + join → `aliasDropCsv = "messy-mcp__createCustomer,messy-mcp__invoiceCreateV2"`.
   Cache for 60s under `aliasdrop:messy-mcp`.

e. For each tool build `fqid = "messy-mcp__" + name`; drop if in the set:

| Tool | fqid | Drop? |
|---|---|---|
| createCustomer | messy-mcp__createCustomer | **yes** |
| customerCreate | messy-mcp__customerCreate | no |
| customerAPIFinalV3 | messy-mcp__customerAPIFinalV3 | no |
| customerFind | messy-mcp__customerFind | no |
| customerSearch | messy-mcp__customerSearch | no |
| customerLookup | messy-mcp__customerLookup | no |
| invoiceCreateV1 | messy-mcp__invoiceCreateV1 | no |
| invoiceCreateV2 | messy-mcp__invoiceCreateV2 | **yes** |
| invoiceCreateLegacy | messy-mcp__invoiceCreateLegacy | no |
| lookup | messy-mcp__lookup | no |
| create | messy-mcp__create | no |
| list | messy-mcp__list | no |

f. Rewrite body with the 10-tool array, stamp `x-mcp-tools-filtered: 2`.

#### 5. Wire response (what the LLM actually sees)

```http
HTTP/1.1 200 OK
x-mcp-tools-filtered: 2

{ "jsonrpc":"2.0","id":1,"result":{"tools":[ ...10 tools, no createCustomer, no invoiceCreateV2... ] } }
```

### Flow B — `tools/call` for an alias (the rewrite path)

A stale agent that cached `tools/list` from before the filter was deployed
still has `createCustomer` in its function-calling schema and the LLM picks
it. The rewrite layer rescues it.

#### 1. Wire request

```http
POST https://apimopenai99.azure-api.net/messy-mcp/mcp HTTP/1.1

{ "jsonrpc":"2.0","id":2,"method":"tools/call",
  "params": { "name":"createCustomer",
              "arguments": {"first":"Ada","last":"Lovelace","email":"ada@example.com"} } }
```

#### 2. APIM `<inbound>` — canonical rewrite

a. `requestedTool = "createCustomer"`, `requestedFqid = "messy-mcp__createCustomer"`.
b. `cache-lookup-value key="canon:messy-mcp__createCustomer"` → miss.
c. Cosmos query:

```sql
SELECT VALUE c.primary.name
FROM c
WHERE c.id = "messy-mcp__createCustomer"
   OR ARRAY_CONTAINS(c.aliases, "messy-mcp__createCustomer")
```

d. Cosmos returns: `{ "Documents": ["customerCreate"] }`.
   The match is on `ARRAY_CONTAINS(c.aliases, ...)` for the `messy-mcp__customerCreate` doc.

e. `canonicalTool = "customerCreate"`. Cache for 60s.
f. Body rewrite:

```json
{ "jsonrpc":"2.0","id":2,"method":"tools/call",
  "params":{ "name":"customerCreate",
             "arguments":{"first":"Ada","last":"Lovelace","email":"ada@example.com"} } }
```

#### 3. Backend executes the canonical, returns success.

#### 4. APIM `<outbound>`

- Stamps `x-mcp-canonical-rewrite: createCustomer -> customerCreate`.
- The filter block also runs but `result.tools` is null on a `tools/call`
  response → no-op.

#### 5. Wire response

```http
HTTP/1.1 200 OK
x-mcp-canonical-rewrite: createCustomer -> customerCreate
```

### Why `customerCreate` was elected canonical (not `createCustomer`)

The election runs in [`apps/dup-resolver/elect.py`](../../apps/dup-resolver/elect.py)
with a deterministic weighted score. Applied to this cluster's two
surviving members (both from `messy-mcp` — `Create_Customer` was already
gone after the wire-name collision):

| Signal | Weight | `createCustomer` | `customerCreate` |
|---|---|---|---|
| `governed` (server = `governed-mcp`) | 0.30 | 0 | 0 |
| `name` regex | 0.10 | **0.10** ✓ | **0.10** ✓ |
| `domain` prefix (`finance` / `customer` / …) | 0.15 | 0 — starts with `create` | **0.15** ✓ — starts with `customer` |
| `verb` (last camel-split token in approved set) | 0.10 | 0 — last token = `Customer` | **0.10** ✓ — last token = `create` |
| `desc` ≥ 80 chars | 0.15 | **0.15** | **0.15** |
| `guidance` words ("USE WHEN" / "DO NOT USE") | 0.20 | 0 | 0 |
| **Total** | **1.00** | **0.35** | **0.50** ◀ winner |

The score breakdown stored on the Cosmos doc (`score: 0.5`,
`score_breakdown: {governed:0, name:0.1, domain:0.15, verb:0.1, desc:0.15, guidance:0}`)
is the receipt of this exact calculation.

If a `governed-mcp` member ever joins this cluster (e.g. someone authors
`customer_create` on the governed side), it would score
`0.30 + 0.10 + 0.15 + 0.10 + 0.15 = 0.80` and automatically take over as
canonical on the next ingest run — no manual override needed.

### Verification queries you can run right now

```sql
-- The exact rewrite query the policy issues for the alias
SELECT VALUE c.primary.name
FROM c
WHERE c.id = "messy-mcp__createCustomer"
   OR ARRAY_CONTAINS(c.aliases, "messy-mcp__createCustomer")
-- → ["customerCreate"]

-- The exact filter query the policy issues for messy-mcp
SELECT VALUE c.aliases
FROM c
WHERE c.canonical_server = "messy-mcp"
   OR EXISTS(SELECT VALUE m FROM m IN c.members WHERE m.server = "messy-mcp")
-- → [ ["messy-mcp__createCustomer"], ["messy-mcp__invoiceCreateV2"] ]

-- Same filter query for governed-mcp — no aliases targeting it yet
SELECT VALUE c.aliases
FROM c
WHERE c.canonical_server = "governed-mcp"
   OR EXISTS(SELECT VALUE m FROM m IN c.members WHERE m.server = "governed-mcp")
-- → all empty arrays → x-mcp-tools-filtered: 0 on governed-mcp/tools/list

-- Querying for a tool name that doesn't exist (the fail-open path)
SELECT VALUE c.primary.name
FROM c
WHERE c.id = "governed-mcp__createCustomer"
   OR ARRAY_CONTAINS(c.aliases, "governed-mcp__createCustomer")
-- → []  → policy returns requestedTool unchanged → request passes through
```
