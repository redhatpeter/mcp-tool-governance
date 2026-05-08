# APIM Policies

Versioned APIM policy artifacts. The source of truth for the design behind each
policy is [docs/ARCHITECTURE.md §15](../../docs/ARCHITECTURE.md). This directory
holds the deployable form so it can be diffed, reviewed, and (eventually)
deployed via APIM Policy Fragments + Terraform.

## Files

| File | Scope | Purpose |
|---|---|---|
| [canonical-rewrite.policy.xml](canonical-rewrite.policy.xml) | MCP server (per imported API) | JWT validation, rate limiting, and canonical-name rewrite for `tools/call` JSON-RPC frames. Fails open on Cosmos errors. |

## Where it attaches

Azure Portal → **APIs → MCP Servers → \<server\> → MCP → Policies**.
Replaces the default empty `<inbound>` block. Apply per MCP server (e.g. once
on `governed/mcp`, once on each `<domain>-raw/mcp`, etc.).

## Prerequisites

The policy assumes the following are configured on the APIM instance hosting
the MCP server. PoC target: **`apimopenai99`**.

### 1. APIM system-assigned managed identity

```bash
APIM_NAME=apimopenai99
APIM_RG=<your-rg>

az apim update -n "$APIM_NAME" -g "$APIM_RG" --set identity.type=SystemAssigned
APIM_MI=$(az apim show -n "$APIM_NAME" -g "$APIM_RG" --query identity.principalId -o tsv)
echo "APIM MI: $APIM_MI"
```

### 2. Cosmos data-plane role assignment

The policy reads from container `mcp-canonical-map` in database `governance`
on Cosmos account `cosmos-ws`. APIM's MI needs the built-in **Cosmos DB Data
Reader** role (`00000000-0000-0000-0000-000000000001`):

```bash
COSMOS_ACCOUNT=cosmos-ws
COSMOS_RG=<cosmos-rg>

az cosmosdb sql role assignment create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$COSMOS_RG" \
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
| `cosmos-ws.documents.azure.com` | Your Cosmos account hostname | Already correct if you reused `cosmos-ws` per the architecture. |

For a production-grade flow these become **APIM Named Values** (or Key Vault
references) and the policy uses `{{tenant-id}}` etc. — see ARCHITECTURE §24
#10 (Policy Fragments).

## Cosmos document shape (assumed by the policy)

```json
{
  "id": "<requestedToolName>",
  "primary": { "name": "<canonicalToolName>", "...": "..." },
  "aliases": ["..."]
}
```

If `id == primary.name` the request is already canonical and the rewrite
branch is a no-op. See ARCHITECTURE §13–§14 for the full canonical_map design.

## Failure mode

**Fail-open.** `send-request` uses `ignore-error="true"` and the value-set
guard returns the originally-requested tool name on any Cosmos error or
missing document. To switch to fail-closed, set `ignore-error="false"` and
remove the null guard in step 3b.

## Testing

There is no automated test for this policy yet. Manual smoke test:

1. Insert a doc with `id="foo_bar"` and `primary.name="canonical_foo"` into
   `mcp-canonical-map`.
2. Issue an MCP `tools/call` with `params.name="foo_bar"` against the MCP
   server endpoint.
3. Confirm:
   - Backend receives `params.name="canonical_foo"`.
   - Response carries `x-mcp-canonical-rewrite: foo_bar -> canonical_foo`.
   - App Insights shows the rewrite header in the request trace.
4. Re-issue within 60s; verify cache hit (no Cosmos call in APIM trace).

A scripted version of this will land in `tools-cli/` during PoC week 1.
