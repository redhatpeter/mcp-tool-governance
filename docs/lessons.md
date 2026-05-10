# Lessons Learned

Running notes from building the MCP Tool Governance PoC. Append new lessons as
they happen; don't rewrite history. Each entry: **date — short title**, then a
few lines on what we hit and what to do (or avoid) next time.

---

## 2026-05-10 — Cosmos `cosmoslab82658` has local auth disabled too

**Symptom:** First run of the new `canonical_map.py` writer with
`COSMOS_KEY_FILE` set returned `(Unauthorized) Local Authorization is
disabled. Use an AAD token to authorize all requests.` on the very first
metadata call (`GetDatabaseAccount`).

**Root cause:** Same Azure Policy pattern as `common-open-ai` —
`Cosmos_DisableLocalAuth_Modify` (or equivalent) re-disables the master
key after any path that toggles it off. Doesn't matter that `az cosmosdb
keys list` returns a key; the data plane refuses it.

**Fix:** unset `COSMOS_KEY` / `COSMOS_KEY_FILE` and let the writer fall
through to `DefaultAzureCredential`. The signed-in user already had
`Cosmos DB Built-in Data Contributor`
(`00000000-0000-0000-0000-000000000002`) at account scope, so AAD
worked first try.

**Lesson:** assume *every* PaaS account in this subscription has local
auth disabled or about to be — design auth precedence (key → AAD)
universally, never key-only. The optional-key path is what lets the
writer no-op cleanly when an environment hasn't set up either.

---

## 2026-05-10 — Demo props in a CI-linted directory will fail your linter eventually

**Symptom:** `validate-mcp-tools` had been silently failing for ~12 hours on
every push that touched `tools-cli/lint.py` or `apim/openapi/**`. The linter
correctly flagged 22 errors against `apim/openapi/finance-messy.json` — the
spec we **intentionally** litter with E004/E005/E006 violations to demo Act 1.

**Root cause:** demo prop sat in the same directory the CI workflow globs.
The demo's whole point is that this spec fails lint, so we couldn't just
"clean it up". And the failure was rare-trigger because the workflow's
`paths:` filter only matched the lint script + the spec dir itself.

**Fix:** added an `unmanaged:` list to `apim/openapi/_servers.yaml`. The
linter declares those stems (so E007 still passes — the spec is a recognized
file) but skips per-operation rules **only when invoked via the default
glob**. When the user names a file explicitly on the command line
(`python3 tools-cli/lint.py apim/openapi/finance-messy.json`), the
exemption is bypassed and you get the full 22-error report — which is
exactly what Act 1 of the customer demo runs.

**Lesson:** if a directory contains both "the gold standard" and "the
counter-example", give your linter a way to tell them apart. Default-glob
mode = "be a good CI citizen"; explicit-file mode = "give me everything".
And add a watch on any CI workflow whose path filter is so narrow it might
not have run in days — silent failures hide there.

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

---

## 2026-05-08 — Wire-name collision dispatches deterministically; collided operation is silently unreachable

**Experiment:** Called `tools/call name=createCustomer` against `messy-mcp`
three times. Watched ngrok request inspector to see which backend path
APIM dispatched to.

`createCustomer` is the wire name produced by APIM camelCasing **two**
distinct operations:
- `createCustomer` (operationId, camelCase original)  → `/messy/createCustomer`
- `Create_Customer` (operationId, PascalCase + underscore) → `/messy/Create_Customer`

**Result:** All three calls dispatched to `/messy/Create_Customer`.
None reached `/messy/createCustomer`. The behavior is **deterministic**
across attempts — not random / round-robin / load-balanced. Likely
alphabetical-by-operationId (`Create_Customer` sorts before
`createCustomer` in ASCII because uppercase C precedes lowercase c).

**Implications:**

1. **Layer 2 (dispatch) confirmed broken under collision.** Even if the
   LLM picks the "right" tool based on rich descriptions — even if the
   MCP host preserves both tool entries in its tool list — the gateway
   still routes both to the same backend. **Descriptions cannot recover
   from a name collision.** The name *is* the dispatch key.
2. **One operation is silently unreachable.** The runner-up in the
   collision is dead: no error, no log, no warning. It's deployed,
   discoverable in the source spec, listed in the Portal Tools blade,
   and reachable via direct HTTP call to its `/messy/createCustomer`
   path — but **not callable through the MCP server it was supposed
   to be exposed by**. This is the most dangerous failure mode we've
   seen: a deployed-but-unreachable tool that looks healthy by every
   normal metric.
3. **Determinism = silent regression risk.** Because the choice is
   stable (alphabetical), things will work consistently in dev/test —
   right up until someone renames an operation in a way that changes
   the alphabetical winner. The "working" tool can flip overnight with
   no code change to the failing path.

**For the PoC demo:** This is the strongest single piece of evidence
for governance. We can show: "Here's an MCP server with 13 declared
operations. Only 12 are advertised. Only 12 are callable. One is
**deployed but functionally dead** — and you cannot tell from any
Portal screen, log, or metric that's the case. Without the registry
+ post-normalization collision check, you ship this to prod."

**Action items:**
- Demo script: include a `tools/call` against the collided wire name
  + show ngrok dispatching to one path while the other is starved.
- L1 CI gate must catch this *before* import. Spec authors do not see
  it; gateway operators do not see it; only post-normalization analysis
  catches it.

---

## 2026-05-08 — APIM-MCP forwards empty body to backend on POST tools/call

**Symptom:** During the dispatch experiment, every POST operation we
called via `tools/call` received an empty body at the backend. FastAPI
responded with 422 `json_invalid: Expecting value` and `input: {}`.

GET operations worked (e.g. `tools/call name=lookup args={q:"acme"}` →
`/messy/lookup?q=acme` 200), because GET parameters travel as query
strings which APIM apparently serializes correctly.

**Likely cause:** APIM is not lifting `params.arguments` from the
JSON-RPC envelope into the HTTP request body when dispatching to the
backend operation. Or it's mapping `arguments` only to query/path
parameters and not to `requestBody`.

**Open questions:**
- Is this configurable per-operation (some APIM property)?
- Is there a bind-by-name vs bind-by-position issue between the
  MCP `arguments` object and the OpenAPI `requestBody.content.application/json.schema`?
- Does the `set-body` policy need to be added to the MCP server's
  inbound policy chain to map JSON-RPC `params.arguments` → backend
  body? If yes, this is a *required* policy for any MCP server that
  exposes POST/PUT/PATCH operations — and it's not documented anywhere
  we can find.

**For the PoC:** Need to resolve before the canonical-rewrite demo
because rewriting the name is pointless if the body never arrives.
Three avenues to try:
1. Inspect what an existing working APIM-MCP example does (search
   azure-samples for a POST tool example).
2. Add a small inbound `set-body` policy that constructs the backend
   body from `context.Request.Body` (the MCP envelope).
3. Try declaring the body parameters as individual query parameters
   in the OpenAPI spec instead of a `requestBody` object.

**Severity:** Blocker for any POST-based PoC scenario, including
`finance_customer_create`, `finance_invoice_create`,
`finance_payment_approve`. GET-based scenarios (`finance_quote_get`,
`finance_invoice_list`, `finance_customer_search`) are unaffected.

---

## 2026-05-08 — Empty-body finding is a KNOWN APIM bug, only affects v1 SKUs

**Update to previous finding.** Researched Microsoft Q&A and found this
is a **known, acknowledged APIM bug** with an official explanation and
a workaround.

**Source:** https://learn.microsoft.com/en-us/answers/questions/4371821/

> "Hi folks, sincere apologies for the technical difficulties you are
> experiencing. This bug is a known issue which we fixed in October.
> However, due to varying release cycles and timelines for the different
> APIM SKUs, this fix hasn't yet been rolled out across all APIM tiers.
> ... we are currently in the process of rolling out a new update
> containing the aforementioned fix for v1 SKUs (Basic, Standard,
> Premium) under the 'AI Gateway Early' update group ... The fix has
> already been rolled out for some time now to our v2 offerings
> (Basicv2, Standardv2, Premiumv2)."
> — Bruce Moe, Microsoft Employee, 2025-12-16

**Affected tiers:** Developer, Basic, Standard, Premium (v1 / "classic").
**Already fixed in:** Basicv2, Standardv2, Premiumv2.

**Our APIM (`apimopenai99`) is Developer (classic)** — directly affected.

**Two paths forward:**

1. **Apply the documented workaround** (recommended for the PoC):

   ```xml
   <policies>
     <inbound>
       <base />
       <set-body>@(context.Request.Body.As<JObject>()["params"]["arguments"].ToString())</set-body>
     </inbound>
     ...
   </policies>
   ```

   This extracts `params.arguments` from the JSON-RPC envelope and uses
   it as the backend HTTP body. It must be applied at the **MCP server
   policy** level (not the API level — the API is the auto-generated MCP
   wrapper that we don't edit directly).

2. **Opt the APIM instance into the "AI Gateway Early" update group**
   per [Configure service update settings](https://learn.microsoft.com/en-us/azure/api-management/configure-service-update-settings).
   Per Bruce Moe (Dec 2025), the fix should land "by end of next week"
   for v1 SKUs in that channel. Effective release date unclear today.

**Decision for PoC:** Apply the workaround as part of the canonical-rewrite
policy. This is actually a useful demo point — it's a real-world example
of why governance teams want a **policy seam at the gateway**: an APIM
bug across hundreds of MCP-exposed APIs would otherwise need to be
patched individually. With our pattern, one policy fragment fixes it
fleet-wide.

**For ARCHITECTURE.md:** Add a sub-section to §2 (architecture) or §15
(policy) noting this body-unwrap requirement. Strip-down version of the
policy:

```xml
<!-- Required workaround on v1 APIM tiers as of 2026-05-08:
     APIM-MCP forwards an empty body to backend on POST tools/call.
     Extract params.arguments and forward as the backend body. -->
<set-body>@(context.Request.Body.As<JObject>()["params"]["arguments"].ToString())</set-body>
```

---

## 2026-05-08 (cont.) — The community workaround does NOT work for APIM-MCP

**Tested empirically.** Attached the suggested unwrap policy to
`governed-mcp` (the MCP-typed API) via ARM:

```xml
<inbound>
  <base />
  <set-body><![CDATA[@{
      var body = context.Request.Body.As<JObject>(preserveContent: true);
      if (body != null && (string)body["method"] == "tools/call")
          return body["params"]["arguments"].ToString();
      return context.Request.Body.As<string>(preserveContent: true);
  }]]></set-body>
</inbound>
```

**Result:** ALL operations (GET and POST) return 500 Internal Server Error.

**Diagnosis:** The MCP server's policy chain runs against the inbound
JSON-RPC envelope **before** APIM-MCP's own routing/translation layer
kicks in. The `<set-body>` mutates the body that APIM-MCP itself needs
to parse (`{"jsonrpc":..., "method":"tools/call", "params":{...}}`).
After we unwrap, APIM-MCP can no longer read `params.name` to pick the
backend operation, so it 500s.

The Q&A thread shows the same outcome — Chris Hammond (the original
reporter) tried the unwrap policy and also hit a 500. Krishna's
suggestion was theoretical and was never confirmed working by any
non-Microsoft user. Bruce Moe (Microsoft Employee) later acknowledged
the bug as a platform-side issue that needed a platform-side fix.

**Conclusion:** There is **no working policy-level workaround on v1 SKUs**.
Three real options:

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Wait for v1 rollout** | Zero work, "right" fix | ETA "end of next week" per Microsoft Dec 2025 — may have landed already; need to retest periodically |
| **B. Migrate APIM to v2 SKU** | Fix is already deployed | Cost + migration effort; v2 SKUs (Basicv2/Standardv2/Premiumv2) only |
| **C. PoC scope adjustment** | Demo proceeds | GET-only canonical-rewrite scenarios (still plenty to show) |

**Decision for now:** Option C for the demo, but also **periodically retest
A** — the fix may have rolled to our instance since Dec 2025. As of today
(2026-05-08) we still see the bug, so the rollout to Developer SKU has
not landed for us.

**Demo impact:** Of 8 governed ops, 5 are GET (`finance_customer_get`,
`finance_customer_search`, `finance_invoice_get`, `finance_invoice_list`,
`finance_quote_get`) — plenty for the canonical-rewrite + alias demo. The
3 POST ops (`finance_customer_create`, `finance_invoice_create`,
`finance_payment_approve`) become "demonstrated as discoverable but
currently blocked by APIM platform bug."

This is itself a useful narrative point: **the gateway is software with
bugs, and a governance pattern that puts a policy seam between the LLM
and the backend gives you a place to add platform-bug workarounds when
they ship — without changing every backend.**

---

## 2026-05-08 — APIM-MCP POST bug is *not* the empty-body bug; it's last-write-wins, and it reproduces on Basic v2

**What we actually found (correcting earlier hypothesis):** The bug is
**not** "empty body forwarded to backend." We were misreading the
FastAPI error. `"input":{}` in the pydantic error object is the
*context*, not the raw bytes. Inspecting the wire with the ngrok
inspector (`http://127.0.0.1:4040/api/requests/http`) revealed the
actual symptom:

For `tools/call` with `arguments = {"name":"X","email":"Y","tier":"gold"}`
APIM forwards a body of exactly **4 bytes: `gold`** — only the *last*
argument's value, no JSON envelope, no field names. Last-write-wins
serialization.

**Cross-tier confirmation:** Spun up a second APIM instance
`ai-gateway-general` (RG `rg-general-ai`, **Basic v2**, **West US**) —
the SKU+region Microsoft claims has the empty-body fix from
`release-service-2026-03` (Q&A 4371821). Imported the same
`finance-governed` OpenAPI, exposed the same MCP server, ran the same
`financeCustomerCreate` payload. Backend received: `body(len=4): 'gold'`.
**Identical symptom.**

**Implications:**
1. This is **not** the empty-body bug fixed in `release-service-2026-03`.
   It is a **separate (or regressed) bug** in APIM's MCP request-body
   serialization path.
2. Affects **both v1 (Developer/stv2.1) and v2 (Basic v2) tiers**, in
   **two different regions**. Tier migration is **not** a workaround.
3. The earlier "Option B: migrate to v2" in the previous lesson is
   **invalid** — strike it. Only Options A (wait) and C (GET-only demo)
   remain viable.
4. The bug report we considered duplicative of Q&A 4371821 is actually
   a **distinct bug**. Filed as Azure-Samples/AI-Gateway issue **#315**.

**Smoking-gun repro (works on any APIM with an MCP server pointing at a
backend you can sniff):**

```bash
curl -X POST "$MCP_URL" \
  -H "Ocp-Apim-Subscription-Key: $KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"financeCustomerCreate",
                 "arguments":{"name":"X","email":"Y","tier":"gold"}}}'
# Backend receives body: 'gold' (4 bytes). Expected: full JSON object.
```

**Methodological lesson:** When a backend reports "JSON decode error,"
**always inspect the actual wire bytes** before theorizing about the
gateway. A 1-line ngrok session would have saved us hours of pursuing
the wrong root-cause hypothesis.

---

## 2026-05-10 — `tee` swallows exit codes; CI silently passed a DUPLICATE verdict

**Symptom:** `similarity-check.yml` returned green even when
`check_pr.py` exited non-zero on a real DUPLICATE. The job log showed the
red verdict text but the step succeeded.

**Root cause:** `python check_pr.py … | tee verdict.md` returns `tee`'s
exit code (always 0), not the script's. The synthetic duplicate test
caught this — the gate was theatre, not a gate.

**Fix:** add `set -o pipefail` at the top of the run script and quote
your scripts as `bash -eo pipefail`. Verified by re-running PR #1 with
the fix in place: ❌ failure on DUPLICATE, ✅ pass on OK. Commit `26d32d8`.

**Generalization:** Any CI step that pipes the gate output to `tee` /
`grep` / a paginator needs `pipefail` or the gate is a no-op.

---

## 2026-05-10 — Azure AI Search accumulates ghost docs without explicit reconciliation

**Symptom:** After renaming a few `messy-mcp` operations from snake_case
to camelCase upstream, the `mcp-tool-fingerprints` index still contained
the old snake_case docs. They quietly inflated cluster sizes and
generated false-positive DUPLICATE verdicts on clean PRs.

**Root cause:** `ingest.py` originally only **upserted**. AI Search
treats unseen-this-run docs as still-valid; nothing prunes them. With
authored specs as the source-of-truth, the index drifts every time an
op is renamed or removed.

**Fix:** Option A reconciliation in `ingest-on-merge.yml` — after
upserting, compute `index_keys − authored_keys` and call
`delete_documents()` on the difference. Log the count
(`deleted_stale: N`). First live run dropped 8 stale docs. Commit `12e865a`.

**Generalization:** Any vector index used as a corpus needs an explicit
"deletes are first-class" pass, not just upserts. Don't assume the
upsert path will reach a steady state on its own.

---

## 2026-05-10 — Azure Policy `CognitiveServices_LocalAuth_Modify` re-disables AOAI key auth

**Symptom:** Workflow runs that worked yesterday started failing with
`401 Unauthorized` from AOAI. Local `curl` against the same endpoint
also failed. Nothing in our repo changed.

**Root cause:** A subscription-scoped Azure Policy
(`CognitiveServices_LocalAuth_Modify`) periodically reverts AOAI accounts
to AAD-only auth. Our CI was using `AOAI_API_KEY`. When policy fires,
our key stops working.

**Workaround (current):** Owner re-enables key auth manually when it
flips off. Verified the toggle re-takes within minutes.

**Long-term fix (P0, deferred):** Migrate CI → Azure auth to GitHub OIDC
+ federated credential + AAD-only auth.
`apps/dup-resolver/config.py` already supports `DefaultAzureCredential`
on both AOAI and Search; the missing piece is the workflow `azure/login`
step + role assignments. See `docs/todo.md` P0 for the full step list.

**Generalization:** Any subscription with Azure Policy enforcement on
Cognitive Services LocalAuth will eventually break key-based CI. Don't
build a CI gate that assumes key auth is permanent.

---

## 2026-05-10 — `gh variable` is the right knob for tunable thresholds

**Symptom:** `CLUSTER_THRESHOLD` was hard-coded in `config.py`. Tightening
it from `0.88` to `0.92` for this repo's demo would have required a code
change on every fork, and would muddy the design-default story.

**Fix:** Read it from a GitHub repo variable in the workflow
(`${{ vars.CLUSTER_THRESHOLD }}`), export as env, let `config.py` fall
back to `0.88` when unset. `gh variable set CLUSTER_THRESHOLD --body 0.92`
is the only command needed to override per-repo. Commit `f1a533f`.

**Generalization:** For any "knob the user might want to turn without
forking the code" — threshold, region, model name — prefer GitHub
**variables** (visible to the workflow log, no secret machinery) over
**secrets**. Secrets are for credentials; variables are for policy.

---

## 2026-05-10 — WSL `az.exe` output has trailing `\r\n` that breaks URL/env-var consumers

**Symptom:** `SUB=$(az.exe account show --query id -o tsv)` followed by
`curl https://.../subscriptions/$SUB/...` returned 404. The URL looked
correct on screen but contained an invisible `\r` before the path
separator.

**Root cause:** When `az` is invoked as `az.exe` from WSL, its stdout
goes through the Windows `cmd` shell, which terminates lines with
`\r\n`. WSL bash captures both characters in `$()` substitution.

**Fix:** Always pipe through `tr -d '\r\n'`:
```bash
SUB=$(az.exe account show --query id -o tsv | tr -d '\r\n')
```

**Generalization:** Any value coming from `az.exe`, `gh.exe`, or any
Windows binary used from WSL needs CR-stripping before it's pasted into
a URL, env var, or HTTP header. Pure-WSL `az` (installed via `apt`)
does not have this problem.
