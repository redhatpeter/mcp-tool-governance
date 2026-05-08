# Lessons Learned

Running notes from building the MCP Tool Governance PoC. Append new lessons as
they happen; don't rewrite history. Each entry: **date — short title**, then a
few lines on what we hit and what to do (or avoid) next time.

---

## 2026-05-08 — `az rest` returns "Bad Request - Invalid URL" against ARM in this environment

**Symptom:** Every `az rest --method GET --url https://management.azure.com/...`
returned an IIS-style HTML "Bad Request - Invalid URL" page, even on
well-formed ARM URLs that worked via `az apim ...` typed CLI.

**Likely cause:** Something in the network path (corporate proxy / TLS
inspector) intercepts the bearer-auth header or the Host. The same calls work
fine through the typed `az` commands because they go via a different code
path / endpoint.

**Workaround:** Use `az apim ...`, `az cosmosdb ...`, `az resource ...`
typed commands. Skip `az rest` for ARM in this environment. For data-plane
calls, the SDK works fine.

---

## 2026-05-08 — APIM-MCP isn't visible via Azure CLI / ARM list endpoints (yet)

**Symptom:** `az provider show --namespace Microsoft.ApiManagement` returns
only `service`, `service/eventGridFilters`, etc. — no `mcpServers` resource
type. `az rest` to `.../service/<name>/mcpServers?api-version=...` returned
the same proxy "Bad Request" (see above).

**Reality:** The APIM-MCP feature exists in the Portal under *APIs → MCP
Servers* and works at runtime, but the public ARM resource type isn't
surfaced through the standard provider metadata that `az` consumes. For now,
**create and edit MCP servers in the Portal**, not via CLI/Terraform.

**Action item for later:** Once the resource type ships, replace Portal
click-through with a Terraform module + `azapi_resource` block.

---

## 2026-05-08 — `apimopenai99` lives in `Default-ActivityLogAlerts`; Cosmos `cosmoslab82658` is in `cosmos-ws` (cross-region)

**What we found:**
- APIM `apimopenai99` → RG `Default-ActivityLogAlerts` → **eastus**
- Cosmos `cosmoslab82658` → RG `cosmos-ws` → **westus**

**Implication:** The canonical-rewrite policy does a `send-request` to Cosmos
on cache miss. Cross-region adds ~60 ms per miss. Acceptable for PoC because
the 60 s cache absorbs most calls. **For pilot/prod**, colocate APIM and
Cosmos in the same region or accept the latency budget explicitly.

---

## 2026-05-08 — APIM system-assigned MI was already enabled

`az apim show --query identity` returned a populated `principalId` even
though we hadn't enabled MI in this session. **Always check first** — don't
assume MI needs to be flipped on, and don't issue a redundant `az apim update`
that triggers a long-running service update.

Principal id (recorded for the Cosmos role assignment):
`29569271-d247-4907-a841-feb848f4016f`.

---

## 2026-05-08 — Azure CLI has no `az cosmosdb sql item create`

**Symptom:** Wanted to seed one canonical_map document via CLI. There's no
typed `cosmosdb sql item create` command.

**Options ranked by effort:**
1. **Portal Data Explorer** — paste JSON, save. ~30 s. *Used this.*
2. `curl` to Cosmos REST API with an AAD bearer token. Requires granting
   the signed-in user a data-plane writer role first.
3. Tiny Python script using `azure-cosmos` SDK + `DefaultAzureCredential`.
   Best for repeatable seeding; will move into `tools-cli/` later.

**Lesson:** For a single doc, the Portal wins. Don't write Python for one
insert.

---

## 2026-05-08 — Port 8000 was already taken on this machine

`uvicorn ... --port 8000` failed with `[Errno 98] address already in use`.
Another long-running uvicorn (`MerchantIQ`) owns 8000.

**Resolution:** Picked port `8088` for `finance-fakes`. Pick uncontested
ports up front; the cost of `ss -ltn | grep :PORT` is zero.

---

## 2026-05-08 — ngrok via snap requires authtoken before any tunnel works

**Symptom:** `ngrok http 8088` appeared to start but produced no log output
in headless mode and the local 4040 admin API took a moment to come up.

**Root cause:** Free-tier ngrok now refuses to open a tunnel until
`ngrok config add-authtoken <TOKEN>` is run once. Without it, the agent
silently fails to register.

**Resolution:**
1. `sudo snap install ngrok`
2. Create free account at https://dashboard.ngrok.com/signup
3. `ngrok config add-authtoken <TOKEN>` (writes
   `/home/plee/snap/ngrok/<rev>/.config/ngrok/ngrok.yml`)
4. `ngrok http 8088` — query `http://127.0.0.1:4040/api/tunnels` to read the
   public URL.

**Caveat:** Free-tier subdomain rotates every restart. Anything that captured
the URL (APIM imports, OpenAPI `servers[0]`, browser tabs) becomes stale
after a restart. **Do not commit the OpenAPI JSONs with the live URL** —
keep them with the `https://REPLACE-WITH-NGROK.ngrok-free.app` placeholder
in git, regenerate locally each ngrok session.

---

## 2026-05-08 — FastAPI exporting two filtered OpenAPI docs from one app

For the PoC backend we wanted **one** running process but **two** OpenAPI
documents (one per router) so APIM imports two separate APIs.

**Pattern:** keep the routers as `APIRouter(prefix="/governed")` /
`APIRouter(prefix="/messy")`, then expose `/openapi-governed.json` and
`/openapi-messy.json` endpoints that call `fastapi.openapi.utils.get_openapi`
and filter `paths` by prefix. Accept a `?server=...` query param so the
exported `servers[0].url` can be set to whatever public URL APIM should
call (ngrok URL, Container App FQDN, etc.) without redeploying the app.

**Why this matters:** APIM imports operations using the OpenAPI's `servers`
field as the backend URL. If you forget to set it, APIM defaults to whatever
hostname you pasted the file from — usually wrong.

---

## 2026-05-08 — Modeling "tool overloading" in OpenAPI

ARCHITECTURE §1 lists "three versions of `invoice_create` with different
schemas under the same name" as a failure mode. **OpenAPI doesn't allow
duplicate `operationId`** values in one spec, so we can't literally express
this in a single API.

**Workaround in `messy_router.py`:** ship three close-named operations
(`invoice_create_v1`, `_v2`, `_legacy`) with **deliberately different
request schemas** (different field names, different required fields). The
resolver still needs to cluster them as semantic duplicates. This faithfully
models the *consumer-facing* problem — agents see three near-identical names
with confusing schemas — without violating the OpenAPI spec.

---

## 2026-05-08 — APIM rejects case-insensitively-duplicate `operationId`

**Symptom:** Importing `finance-messy.json` into APIM failed with:
> Parsing error(s): Cannot have multiple operations with the same
> operationId: CreateCustomer

The OpenAPI doc actually had `createCustomer` (camelCase) **and**
`CreateCustomer` (PascalCase) — distinct strings, but APIM normalizes
operationId case for routing/storage and treats them as the same.

**Workaround:** Renamed `CreateCustomer` → `Create_Customer` (PascalCase +
underscore) in `messy_router.py`. Still demonstrates the "naming chaos"
collision in the demo, but case-insensitively unique so APIM accepts it.

**Bonus finding:** This is itself a real-world data point — case-only
collisions are *invisible* at the OpenAPI authoring layer but **fatal** at
the APIM import layer. Worth surfacing in the L1 CI gate (`tools-cli`
should warn on case-insensitively colliding operationIds within a single
spec).

---

## 2026-05-08 — APIM-MCP auto-generates tool names from `summary`, NOT `operationId`

**Symptom:** After exposing `finance-governed` and `finance-messy` as MCP
servers, an MCP `tools/list` returned tool names that were **camelCased
versions of the OpenAPI `summary`** field — not the `operationId` we set:

| OpenAPI `operationId` | APIM-MCP tool name |
|---|---|
| `finance_customer_create` | `createACustomer` |
| `finance_quote_get` | `getAMarketQuoteForASymbol` |
| `finance_invoice_list` | `listInvoicesOptionallyFilteredByCustomerOrStatus` |
| `createCustomer` | `collisionCreateCustomerCamelCase` |
| `Create_Customer` | `collisionCreateCustomerPascalCaseUnderscore` |
| `customer_find` | `semanticDupFindCustomersMatchingATerm` |
| `lookup` | `ungroupedGenericLookup` |

The summary tag prefixes (`[collision]`, `[semantic-dup]`, `[ungrouped]`)
were swallowed into the name and lost their visual marker.

**Implications:**

1. The whole "rewrite alias → canonical operationId in the policy" story
   doesn't work as-written. The canonical names APIM dispatches on are
   not our `operationId`s — they're whatever APIM auto-generated. Our
   seeded `canonical_map` Cosmos doc must match **APIM's tool name**
   on both sides of the rewrite.
2. There is now effectively a **fifth failure mode** the architecture doc
   didn't anticipate: *gateway-induced naming drift*. A clean backend
   `operationId` (`finance_quote_get`) gets re-uglified by the gateway
   into `getAMarketQuoteForASymbol` before any agent sees it.

**Resolution chosen for PoC:** Override the per-tool name + description in
the APIM MCP server editor (Portal → MCP Servers → \<server\> → Tools →
edit each tool) to restore our intended canonical names. ~21 tools to
rename in the PoC; tedious but one-time.

**Action items:**
- Add to `tools-cli` a check: warn when `operationId` differs significantly
  from APIM's would-be auto-generated name, since the auto-generated form
  is what callers actually see.
- Consider whether L1 CI should *post-import* fetch APIM's `tools/list` and
  diff against the registry — if APIM mangled a name, fail the PR.
- For Terraform later, set the explicit `displayName` on each MCP-server
  tool resource so we never depend on summary-derived names.

---

## 2026-05-08 — Deleting an APIM API silently fails in the Portal if an MCP server references it

**Symptom:** Clicked **Delete** on `finance-governed` in the Portal. UI
flashed a "deleted" toast, but the API kept showing in the list. Re-opening
the blade still showed it. `az apim api list` confirmed it was still there.

Trying to delete it via CLI surfaced the real error:

```
(ValidationError) API cannot be deleted since it is referenced by at least
one MCP tool. Delete the MCP tools referencing this API before deleting
the API.
```

**Root cause:** When you "expose an API as an MCP server," APIM creates a
**second API resource** of `properties.type = "mcp"` (e.g. `governed-mcp`)
that references the source API. The source API can't be deleted while the
MCP-typed API still exists. The Portal swallows this error in some flows.

**Gotchas finding the MCP-typed APIs:**
- `az apim api list` does **not** show MCP-typed APIs. They only appear
  via the ARM REST list with a **preview** api-version.
- Working api-version: `2024-06-01-preview` (also `2024-10-01-preview`,
  `2025-03-01-preview`). The GA version `2024-05-01` hides them.
- Filter: `properties.type == "mcp"`.

**Working delete sequence (CLI):**

```bash
SUB=<sub-id>
RG=<rg>
APIM=<apim-name>
AV=2024-06-01-preview
BASE="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/service/$APIM/apis"

# 1. Find MCP-typed APIs
az rest --method get --uri "$BASE?api-version=$AV" \
  | python3 -c "import sys,json; [print(a['name']) for a in json.load(sys.stdin)['value'] if a['properties'].get('type')=='mcp']"

# 2. Delete MCP servers FIRST, then their source APIs
for ID in governed-mcp messy-mcp finance-governed finance-messy; do
  az rest --method delete --uri "$BASE/$ID?api-version=$AV"
done
```

**Action items:**
- For Terraform: model the dependency explicitly so `terraform destroy`
  tears down the MCP-typed API before the source API.
- For runbooks: never trust the Portal "delete" toast for MCP-related
  resources — always confirm with `az apim api list` + the preview-version
  ARM REST list filtered by `type=mcp`.
- File a Portal bug: silent failure on delete-with-dependency is a footgun.

---

## 2026-05-08 — APIM-MCP camelCases tool names on the wire even when the Portal Tools UI shows them with underscores

**Symptom:** After the second import (this time setting OpenAPI `summary` to
the exact desired tool name like `finance_customer_create` and
`Create_Customer`), the Portal **MCP Server → Tools** blade displayed the
names with underscores preserved — exactly as authored. Looked perfect.

But an actual MCP `tools/list` call against the gateway returned
**camelCased** names anyway:

| Authored `summary` (Portal UI shows this) | What `tools/list` actually returns |
|---|---|
| `finance_customer_create` | `financeCustomerCreate` |
| `finance_quote_get` | `financeQuoteGet` |
| `Create_Customer` | `createCustomer` |
| `customer_create` | `customerCreate` |
| `CustomerAPI_Final_v3` | `customerApiFinalV3` |
| `createCustomer` | `createCustomer` |

**The kicker:** Two of our four "collision" anti-pattern operations
(`createCustomer` and `Create_Customer`) collapsed into a **single wire-name
`createCustomer`**. APIM's normalizer turned a *designed-as-distinct*
collision pair into a *literal duplicate* in `tools/list`. The MCP client
cannot distinguish them. We declared 13 messy operations; only 12 unique
names are advertised.

**Implications:**

1. **Portal display ≠ wire reality.** Operators reading the Tools blade
   are looking at a different name than agents see. This is a footgun for
   troubleshooting (`"why is my agent not finding finance_quote_get?"`
   → because the agent sees `financeQuoteGet`).
2. **Backend `operationId`, OpenAPI `summary`, AND Portal-displayed name
   are all decorative** as far as the wire protocol is concerned. APIM
   has its own normalizer and it always wins.
3. **Gateway-induced naming drift is unavoidable** in the current
   APIM-MCP implementation. Our naming standard
   (`{domain}_{entity}_{verb}`, snake_case) survives in the registry and
   in our specs, but the client sees camelCase.
4. **Collision detection must move into our control plane.** APIM's
   normalizer can collapse two distinct authored names into one wire name
   *without warning*. L1 CI must replicate APIM's normalization rule and
   detect post-normalization collisions before import.

**Action items:**
- Document APIM's normalization rule precisely (write a small Python
  function: `apim_wire_name(summary_or_operation_id) -> str`) and ship
  it in `tools-cli`. The rule appears to be: split on
  `[ _\-]`, lowerCase first token, capitalize subsequent tokens, drop
  separators. Confirm with more samples.
- L1 CI gate: for every PR, compute the post-normalization wire name
  for every operation in every spec and **fail the PR if two operations
  in the same MCP server normalize to the same wire name**.
- Update the canonical_map registry: the **canonical name** field must
  be the wire name APIM will actually advertise, not our authored name.
  (Or store both, with the wire name as the lookup key.)
- Update ARCHITECTURE.md §3 (failure modes) to add a 5th: *gateway-
  induced naming drift / silent collision collapse*.
- Update the canonical-rewrite policy: it must rewrite to the **wire
  name** (`financeQuoteGet`), not to the snake_case authored name.
- Demo angle: this is a real and surprising failure mode that vendors do
  not document. Worth showcasing on its own.

**Open question:** can the auto-rename be disabled via APIM extension
properties (`x-ms-mcp-tool-name`?) or a Terraform `displayName` override
on the MCP-server tool resource? Investigate before redesigning.
