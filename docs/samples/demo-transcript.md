# Demo Transcript — Pre-captured Clean Run

**Captured:** 2026-05-09T18:18:26Z
**Script:** [`demo/run-demo.sh`](../../demo/run-demo.sh) (run with `AUTO=1`)
**Gateway:** `https://apimopenai99.azure-api.net/governed-mcp/mcp`
**Purpose:** Screen-share fallback if Azure / ngrok / lint is unreachable mid-demo.
The output below is byte-for-byte what the script produces on a healthy run
(ANSI escapes stripped for readability).

---

```text

=================================================================
 MCP Tool Governance — 5-minute customer demo 
=================================================================
  Repo: /home/plee/mcp-tool-governance
  Gateway: https://apimopenai99.azure-api.net/governed-mcp/mcp

=================================================================
 ACT 1 — The Problem: an ungoverned MCP surface 
=================================================================
  This is what happens when teams ship tools to MCP with no guardrails.
  Same lint we use in CI; runs in <1s and scores the OpenAPI spec.
  $ python3 tools-cli/lint.py apim/openapi/finance-messy.json

[FAIL] finance-messy.json  (13 ops, 22 errors, 13 warnings)
  ERROR   E004  POST /messy/createCustomer                  summary='createCustomer'                      -> wire='createCustomer'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  POST /messy/createCustomer                  summary='createCustomer'                      -> wire='createCustomer'
           action token 'customer' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  warn    W102  POST /messy/createCustomer                  summary='createCustomer'                      -> wire='createCustomer'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E003  POST /messy/Create_Customer                 summary='Create_Customer'                     -> wire='createCustomer'
           collision: POST /messy/createCustomer already produces wire name 'createCustomer'; APIM-MCP will silently drop one
  ERROR   E004  POST /messy/Create_Customer                 summary='Create_Customer'                     -> wire='createCustomer'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  POST /messy/Create_Customer                 summary='Create_Customer'                     -> wire='createCustomer'
           action token 'customer' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  warn    W102  POST /messy/Create_Customer                 summary='Create_Customer'                     -> wire='createCustomer'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  warn    W102  POST /messy/customer_create                 summary='customer_create'                     -> wire='customerCreate'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E005  POST /messy/CustomerAPI_Final_v3            summary='CustomerAPI_Final_v3'                -> wire='customerAPIFinalV3'
           action token 'v3' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  ERROR   E006  POST /messy/CustomerAPI_Final_v3            summary='CustomerAPI_Final_v3'                -> wire='customerAPIFinalV3'
           summary contains a banned version/legacy marker (v1, v2, final, legacy, new, old) — encode versions in the OpenAPI `info.version` field instead
  warn    W102  POST /messy/CustomerAPI_Final_v3            summary='CustomerAPI_Final_v3'                -> wire='customerAPIFinalV3'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E005  GET /messy/customer_find                    summary='customer_find'                       -> wire='customerFind'
           action token 'find' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  warn    W102  GET /messy/customer_find                    summary='customer_find'                       -> wire='customerFind'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  warn    W102  GET /messy/customer_search                  summary='customer_search'                     -> wire='customerSearch'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E005  GET /messy/customer_lookup                  summary='customer_lookup'                     -> wire='customerLookup'
           action token 'lookup' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  warn    W102  GET /messy/customer_lookup                  summary='customer_lookup'                     -> wire='customerLookup'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  POST /messy/invoice_create_v1               summary='invoice_create_v1'                   -> wire='invoiceCreateV1'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  POST /messy/invoice_create_v1               summary='invoice_create_v1'                   -> wire='invoiceCreateV1'
           action token 'v1' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  ERROR   E006  POST /messy/invoice_create_v1               summary='invoice_create_v1'                   -> wire='invoiceCreateV1'
           summary contains a banned version/legacy marker (v1, v2, final, legacy, new, old) — encode versions in the OpenAPI `info.version` field instead
  warn    W102  POST /messy/invoice_create_v1               summary='invoice_create_v1'                   -> wire='invoiceCreateV1'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  POST /messy/invoice_create_v2               summary='invoice_create_v2'                   -> wire='invoiceCreateV2'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  POST /messy/invoice_create_v2               summary='invoice_create_v2'                   -> wire='invoiceCreateV2'
           action token 'v2' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  ERROR   E006  POST /messy/invoice_create_v2               summary='invoice_create_v2'                   -> wire='invoiceCreateV2'
           summary contains a banned version/legacy marker (v1, v2, final, legacy, new, old) — encode versions in the OpenAPI `info.version` field instead
  warn    W102  POST /messy/invoice_create_v2               summary='invoice_create_v2'                   -> wire='invoiceCreateV2'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  POST /messy/invoice_create_legacy           summary='invoice_create_legacy'               -> wire='invoiceCreateLegacy'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  POST /messy/invoice_create_legacy           summary='invoice_create_legacy'               -> wire='invoiceCreateLegacy'
           action token 'legacy' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  ERROR   E006  POST /messy/invoice_create_legacy           summary='invoice_create_legacy'               -> wire='invoiceCreateLegacy'
           summary contains a banned version/legacy marker (v1, v2, final, legacy, new, old) — encode versions in the OpenAPI `info.version` field instead
  warn    W102  POST /messy/invoice_create_legacy           summary='invoice_create_legacy'               -> wire='invoiceCreateLegacy'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  GET /messy/lookup                           summary='lookup'                              -> wire='lookup'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  ERROR   E005  GET /messy/lookup                           summary='lookup'                              -> wire='lookup'
           action token 'lookup' is not in the approved verb list (get, list, search, create, update, delete, summarize, validate, approve, reject, void)
  warn    W102  GET /messy/lookup                           summary='lookup'                              -> wire='lookup'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  POST /messy/create                          summary='create'                              -> wire='create'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  warn    W102  POST /messy/create                          summary='create'                              -> wire='create'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance
  ERROR   E004  GET /messy/list                             summary='list'                                -> wire='list'
           wire name does not start with an approved domain (finance, customer, hr, sales, operations)
  warn    W102  GET /messy/list                             summary='list'                                -> wire='list'
           description lacks 'USE WHEN' / 'DO NOT USE' disambiguation guidance

=== TOTAL: 22 errors, 13 warnings across 1 spec(s) ===

  Result: collisions (E003) — APIM-MCP silently drops dup tools.
          Missing descriptions (W101) — LLMs can't disambiguate.
          Banned legacy markers (E006) — version drift in tool names.

=================================================================
 ACT 2 — Layer 1: design-time gate stops bad tools at the PR 
=================================================================
  Same lint, against the governed spec we curated for this domain.
  $ python3 tools-cli/lint.py apim/openapi/finance-governed.json

[ok] finance-governed.json  (8 ops, 0 errors, 0 warnings)

=== TOTAL: 0 errors, 0 warnings across 1 spec(s) ===

  Result: 0 errors / 0 warnings.
  Wired into .github/workflows/validate-mcp-tools.yml — every PR runs this.
  Bad tools never reach production.

=================================================================
 ACT 3 — Layer 3: runtime canonical rewrite at the gateway 
=================================================================
  Even with L1 in place, you can't force every caller to use the canonical name.
  Legacy callers, federated tools, LLM hallucinations, copy-pasted examples.
  L3 absorbs all that and rewrites to the canonical at the gateway.

  Three curls, same endpoint, different requested tool names:

▸ Test A — canonical name (already correct, no rewrite)
  $ curl -X POST https://apimopenai99.azure-api.net/governed-mcp/mcp ... '"name":"financeQuoteGet"'
  HTTP/1.1 200 OK
  x-mcp-canonical-rewrite: none (financeQuoteGet)

▸ Test B — legacy alias (rewritten to canonical)
  $ curl -X POST https://apimopenai99.azure-api.net/governed-mcp/mcp ... '"name":"get_finance_quote"'
  HTTP/1.1 200 OK
  x-mcp-canonical-rewrite: get_finance_quote -> financeQuoteGet

▸ Test C — different alias (also rewritten)
  $ curl -X POST https://apimopenai99.azure-api.net/governed-mcp/mcp ... '"name":"fetch_quote"'
  HTTP/1.1 200 OK
  x-mcp-canonical-rewrite: fetch_quote -> financeQuoteGet

  Same canonical implementation, three input names. Zero app-code changes.
  Lookup is in Cosmos, cached 60s in APIM, authenticated via managed identity.

=================================================================
 ACT 4 — Layer 2: AI-Search-backed semantic deduplication 
=================================================================
  L1 catches naming drift. L3 absorbs aliases at runtime.
  But what about NEW tools that LOOK fine to the linter but DUPLICATE existing ones?
  L2 runs every tool through Azure OpenAI embeddings + AI Search vector index,
  clusters near-duplicates, elects a canonical, and exposes a PR-time check.

▸ Show all tool clusters across both MCP servers
  $ curl http://127.0.0.1:8089/clusters
  total_tools     = 20
  total_clusters  = 18
  duplicate sets  = 2

  Multi-member clusters (semantic duplicates):
    [clu_messy-mcp__createCustomer]  canonical = customerCreate
        messy-mcp/createCustomer
      * messy-mcp/customerCreate
    [clu_messy-mcp__invoiceCreateV1]  canonical = invoiceCreateV1
        messy-mcp/invoiceCreateV2
      * messy-mcp/invoiceCreateV1

  Cosine ≥ 0.88 in 3072-dim embedding space groups these together.
  Election picked the canonical deterministically — governed/well-named/described wins.

▸ Simulate a developer adding a new tool: 'financeQuoteFetch'
  Imagine this op just landed in a PR against apim/openapi/finance-governed.json.
  The same code runs in CI via .github/workflows/similarity-check.yml.
  $ curl -X POST http://127.0.0.1:8089/similarity -d '{...financeQuoteFetch...}'
  verdict   : DUPLICATE
  threshold : 0.92  (this repo's tightened override; default in config.py is 0.88)
  reason    : top match 'financeQuoteGet' on governed-mcp (score 0.958) >= threshold 0.92;
              reuse the canonical or rename this op

  Top 3 nearest neighbors in the index:
    0.958  governed-mcp/financeQuoteGet [CANONICAL]
    0.679  governed-mcp/financeInvoiceGet [CANONICAL]
    0.671  governed-mcp/financeCustomerGet [CANONICAL]

  Index freshness: oldest top-hit last_seen_utc shown in the markdown footer
  (re-ingested by .github/workflows/ingest-on-merge.yml on every push to main).

  CI exits 1 → the required check fails → PR is blocked from merging.
  See PR #1 history for a captured live run: DUPLICATE 0.958, ❌ failure.
  Bonus: validate-mcp-tools/lint also fails (E005 — 'fetch' not in approved
  verb list). L1 + L2 both firing on the same PR demonstrates defense-in-depth.

  If the developer also DELETED financeQuoteGet in the same PR, the verdict
  would be ℹ️ INFO ('looks like a rename, not a duplicate') — see the
  rename-detected scenario in apps/dup-resolver/tests/run_scenarios.sh.

=================================================================
 BONUS — The eval numbers (the 'so what') 
=================================================================
  Same model (gpt-4o-mini), same 20 prompts, only the tool surface differs:

  | `A_messy` | 36 | 60 | **60.0%** |
  | `B_governed` | 54 | 60 | **90.0%** |
  **Absolute lift (governed − messy): +30.0 percentage points**

  Translation for the customer:
    A messy MCP surface costs you 30 percentage points of agent accuracy.
    Governance is not theatre — it directly moves the eval needle.


=================================================================
 Demo complete. Questions? 
=================================================================
```
