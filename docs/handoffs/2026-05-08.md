# MCP Tool Governance — Session Handoff

**Date:** 2026-05-08
**Author of prior session:** Peter Lee (with GitHub Copilot)
**Purpose:** Resume the V3 MCP Tool Governance work in a fresh VS Code window / new chat thread without losing context.

---

## TL;DR — where we are

- **V3 PoC plan is written and stable.** Source of truth: [docs/ARCHITECTURE.md](../ARCHITECTURE.md). It mirrors v2's 26-section structure but uses APIM-MCP natively (no custom MCP server containers).
- **V3 diagrams are written and stable.** Single file: [docs/ARCHITECTURE-diagrams.md](../ARCHITECTURE-diagrams.md) (Mermaid + draw.io XML).
- **V2 plan lives only in `agent-framework`** (the original `MCP-Tool-Governance-POC-Plan-v2.md`); it was rolled back to its original "custom MCP servers behind APIM aggregator" form and was **not migrated** to this repo.
- **Topology options + upgrade path** are baked into ARCHITECTURE §4.1 and §24, and captured separately in [ADR 0003](../adr/0003-topology-upgrade-path.md) (PoC = B per-domain, Pilot = D governed+raw, Year 1 = +E per-profile, Year 2+ = G multi-APIM only if forced).
- **Repo split is done.** This repo (`mcp-tool-governance`) was extracted out of `microsoft/agent-framework` `backup/<customer>/mcp/` per [ADR 0002](../adr/0002-repo-split.md). Docs were reorganized into `docs/`.
- **No code changes outstanding** — only docs were touched in this session.

---

## File map (where things live)

All paths relative to repo root `mcp-tool-governance/` (this repo).

```
mcp-tool-governance/
├── README.md                               ← orientation + links
└── docs/
    ├── ARCHITECTURE.md                     ← v3 plan (CURRENT source of truth, was MCP-Tool-Governance-POC-Plan-v3.md)
    ├── ARCHITECTURE-diagrams.md            ← v3 diagrams (was v3_architecture.md)
    ├── adr/
    │   ├── 0001-apim-mcp-native.md         ← why APIM-MCP, not custom MCP servers
    │   ├── 0002-repo-split.md              ← why this repo exists
    │   └── 0003-topology-upgrade-path.md   ← B → D → E → G
    └── handoffs/
        └── 2026-05-08.md                   ← THIS FILE
```

**Not migrated to this repo** (still live only in `microsoft/agent-framework` at `backup/<customer>/mcp/`):
- `MCP-Tool-Governance-POC-Plan.md` (v1, historical)
- `MCP-Tool-Governance-PoC-Local-Plan.md` (local-dev variant, historical)
- `MCP-Tool-Governance-POC-Plan-v2.md` (v2, historical)
- `poc/` scaffolded code — was inert in the framework repo (nested `.github/workflows/` don't run); will be rebuilt fresh here per ARCHITECTURE §17.
- `backup/<customer>/apim/APIM-AWSBedrockChain.md` — referenced from ARCHITECTURE §1 + §26 (Bedrock/Vertex federation precedent). Still lives in `agent-framework`.

---

## What was decided this session (key facts)

These were settled in conversation; all are reflected in the v3 doc. Don't re-litigate unless the user asks.

1. **APIM is the MCP server in V3.** No custom MCP server containers. Each imported REST API in APIM gets a native `/mcp` endpoint via the APIM-MCP feature.
2. **L3 enforcement = MCP-server-scoped APIM policy** (Portal: *APIs → MCP Servers → \<server\> → MCP → Policies*). Full ~80-line drop-in policy XML lives in v3 §15 (`validate-jwt` + `rate-limit` + `cache-lookup-value` + `authentication-managed-identity` + `send-request` to Cosmos + `set-body` rewrite + `x-mcp-canonical-rewrite` header).
3. **Cosmos auth = managed identity, no keys.** APIM system-assigned MI + `Cosmos DB Built-in Data Reader` role on the `mcp-canonical-map` container. The `az cosmosdb sql role assignment create` snippet is in v3 §15.
4. **Cosmos document shape**: `{ id: "<requestedToolName>", primary: { apim_mcp_server, apim_operation_id, name: "<canonicalName>" }, aliases: [...], election: {...} }`. If `id == primary.name`, no rewrite occurs (already canonical).
5. **Cache behavior**: 60 s `cache-store-value` keyed by requested tool name. Two walk-throughs in §4 (cold MISS path + warm HIT path + already-canonical no-op).
6. **Caveat**: APIM-MCP supports MCP **tools** only — not resources/prompts. Out of scope for the PoC. If they become must-have AND APIM-MCP still doesn't support them, add a thin custom shim *just for those types* — never for tools.
7. **`--namespace` flag in `azmcp` is unrelated** to APIM-MCP and unrelated to business-domain namespacing. `azmcp --namespace` selects baked-in Azure-service tool groups in the `azmcp` binary; APIM-MCP has no namespace concept either. Domain namespacing in V3 = the `domain.entity.action` naming standard (§9) + one MCP server entity per domain.
8. **Topology = Option B for PoC, Option D for pilot, layer E for Year 1, G only if forced.** §4.1 has the full 7-option table (A–G), 13-criterion side-by-side, and the staged upgrade path with the ASCII ladder.
9. **`messy/mcp` vs `<domain>-raw/mcp`** — these are *different things*. `messy/mcp` is a **demo prop** that exists only to show the four failure modes; drop after the PoC. `<domain>-raw/mcp` is **permanent operational furniture** in Option D — internal-only APIM Product, gives teams day-zero callability before L2 election. Captured in v3 §4.1 + §24 #12.
10. **Doc strategy**: kept v3 as a single hybrid doc (design + plan) for now. Recommended split into `Design.md` + archived `POC-Plan-v3.md` **at end of week 3**, not now. See [Future work](#future-work).
11. **Repo split: DONE.** `backup/<customer>/mcp/` was extracted into this private customer-owned repo (`mcp-tool-governance`). Docs were renamed (`MCP-Tool-Governance-POC-Plan-v3.md` → `docs/ARCHITECTURE.md`, `v3_architecture.md` → `docs/ARCHITECTURE-diagrams.md`) and three ADRs were authored. The `poc/` scaffold was not migrated and will be rebuilt fresh. See [ADR 0002](../adr/0002-repo-split.md).

---

## What was edited this session

In chronological order:

| File | Change |
|---|---|
| `docs/ARCHITECTURE-diagrams.md` (was `v3_architecture.md`) | (Earlier in session — already done) Removed incorrect runtime edge from API Center to Chat UI; cleaned 5 other inconsistencies; aligned Mermaid + draw.io. |
| `MCP-Tool-Governance-POC-Plan-v2.md` *(in `agent-framework`)* | Briefly updated to v3 content, then **rolled back** to its original v2 form via `multi_replace_string_in_file` (6 replacements). Now matches the original v2 again. |
| `docs/ARCHITECTURE.md` (was `MCP-Tool-Governance-POC-Plan-v3.md`) | **Created from scratch** — full 26-section parallel to v2, with V3-native content throughout. |
| `docs/ARCHITECTURE.md` | Added warm-cache HIT walk-through to §4 (in addition to existing cold MISS walk-through) + already-canonical no-op note. |
| `docs/ARCHITECTURE.md` | Added **§4.1 Topology options & upgrade path** — full 7-option table A–G, side-by-side evaluation, staged adoption path B→D→E→G, governed-vs-raw permanence note. Updated TOC. |
| `docs/ARCHITECTURE.md` | Added new **#0** + **#12** to §24 Post-POC Recommendations citing the upgrade path; sharpened **#10** to call out APIM Policy Fragments as load-bearing for Option D. |
| `docs/adr/0001-apim-mcp-native.md`, `0002-repo-split.md`, `0003-topology-upgrade-path.md` | New ADRs authored after repo split. |
| `README.md` | Rewritten from stub to full orientation page (target layout, conventions, Azure environment, links). |

No code files were touched.

---

## Open decisions (user action pending)

### 1. ~~Split `backup/<customer>/mcp/` into its own customer-owned repo~~ — DONE 2026-05-08

Extracted into this repo. ADR 0002 captures the decision. The historical rationale and migration plan are preserved below for reference.

<details><summary>Original recommendation (kept for context)</summary>

**Recommendation: yes, before going much further.** Rationale (full version in prior chat turn):

- `backup/<customer>/mcp/poc/` is a self-contained product (its own `.github/`, `.gitignore`, `docker-compose.yml`) — it thinks it's a repo.
- It lives inside `microsoft/agent-framework`, a public OSS framework. Customer-specific names (the customer, `<apim-instance>`, `<apim-gateway-host>`) **must not be pushed upstream**.
- `.github/workflows/` inside `poc/` are inert (GitHub only runs root-level workflows).
- Can't tag releases, restrict reviewers, enforce CODEOWNERS while it's nested 3 levels deep in someone else's repo.

**Recommended new structure:**

```
<customer>/mcp-governance                       (private, customer-owned)
├── README.md
├── ARCHITECTURE.md                       ← copy of MCP-Tool-Governance-POC-Plan-v3.md
├── ARCHITECTURE-v3-diagrams.md           ← copy of v3_architecture.md
├── ADRS/0001-apim-mcp-native.md
├── ADRS/0002-repo-split.md
├── .github/workflows/                    ← validate-tools.yml, deploy-mcp.yml (now actually runs)
├── apim/policies/canonical-rewrite.policy.xml
├── apps/{frontend,dup-resolver}/
├── infra/terraform/
├── registry/{governed,messy}/
├── profiles/
├── tools-cli/
├── eval/
└── docs/                                 ← archive v1 / v2 / local plans here
```

**Migration script (preserves history):**

```bash
git clone https://github.com/microsoft/agent-framework /tmp/af-extract
cd /tmp/af-extract
git filter-repo --path backup/<customer>/mcp/ --path-rename backup/<customer>/mcp/:
git remote add origin <new-mcp-repo-url>
git push -u origin main
# then promote poc/ contents to repo root in the new repo
# then delete backup/<customer>/ from the agent-framework working copy
```

**Multi-root VS Code workspace** to keep editing both side-by-side:

```jsonc
// AgentFramework-and-MCP.code-workspace at parent of both folders
{
  "folders": [
    { "name": "agent-framework (upstream)", "path": "agent-framework" },
    { "name": "mcp-governance (customer)",       "path": "../6.MCPGovernance/mcp-governance" }
  ],
  "settings": { "files.exclude": { "backup/<customer>/**": true } }
}
```

**Status:** Done. Executed 2026-05-08. ADR 0002 written.

</details>

### 2. Doc split (Design vs PoC Plan)

Deferred to **end of week 3** of the PoC (when the plan-side content stops changing). Don't split mid-PoC. Outline of how to split is in [Future work](#future-work).

### 3. Three Ring 1 Azure-service additions from §A

User has not yet picked these up. Recommended:
- #2 Container Apps Jobs (resolver scheduled rebuild)
- #4 Azure AI Foundry Evaluations (replace custom eval harness in §19)
- #6 APIM Policy Fragments (versioned policy, load-bearing for Option D)

---

## Future work (in rough priority order)

| # | Task | Trigger |
|---|---|---|
| 1 | Execute the repo split (Open decision #1) | User decides to do it |
| 2 | Write `<customer>/mcp-governance/README.md` for the new repo root | After repo split |
| 3 | Write `ADRS/0001-apim-mcp-native.md` (why we abandoned custom MCP servers) | After repo split |
| 4 | Write `ADRS/0002-repo-split.md` (why this split happened) | After repo split |
| 5 | Extract §15 policy XML into a standalone `apim/policies/canonical-rewrite.policy.xml` artifact | When other teams start asking for it |
| 6 | Implement Ring 1 Azure additions (#2, #4, #6 from §A) | Start of PoC week 1 |
| 7 | Build the actual code in `poc/` (per §17 three-week plan) | When 3-week PoC starts |
| 8 | Split v3 doc into `MCP-Tool-Governance-Design.md` + archived `MCP-Tool-Governance-POC-Plan-v3.md` | End of PoC week 3 |
| 9 | Fill in §19 with actual eval numbers | After PoC demo |
| 10 | Write the ADR for the topology upgrade path (B→D→E→G) | When pilot starts (post-PoC) |

---

## Technical context the next session needs

### The user's actual APIM tenant

- **APIM instance:** `<apim-instance>`
- **Gateway URL:** `https://<apim-gateway-host>`
- **Existing MCP servers visible in their portal:**
  - `crs-coigeneration-mcp-dev` — `Source: API`, URL: `/coi-mcp/mcp` (REST→MCP, OpenAPI-derived)
  - `jg-mcptest-api` — `Source: API`
  - `jg-mcptest-server` — `Source: MCP server`, URL: `/learn` (passthrough)
  - `uui-mcp-server` — `Source: MCP server`, URL: `/uui-mcp` (passthrough)

- **Source column meaning:** `API` = APIM derives MCP tools from the imported OpenAPI; `MCP server` = passthrough to a backend MCP server.
- **PoC topology** uses two MCP servers under this same APIM instance: `governed/mcp` and `messy/mcp` (the latter is the demo prop).

### Reused Azure resources (already exist in the customer environment)

- APIM: `<apim-instance>`
- AI Search: `ai102srch193837986` → new index `mcp-tool-fingerprints` (1536-dim)
- Cosmos DB account: `cosmos-ws` → new SQL container `mcp-canonical-map`, PK `/canonical_id`, 400 RU/s
- Azure OpenAI: existing in same RG/sub (chat + embedding deployments)
- Entra tenant: existing

### New Azure resources for the PoC

- RG: `MCP-tool-governance`
- API Center: `apic-mcp-poc`
- Container Apps Env: `cae-mcp-poc` (hosts only Frontend + Dup-Resolver — 2 apps)
- ACR: `acrmcppoc<rand>`
- LAW + AI: `law-mcp-poc`, `appi-mcp-poc`
- Key Vault: `kv-mcp-poc-<rand>`

### V3-vs-V2 quick reference

| | v2 | v3 |
|---|---|---|
| MCP server runtime | 2 custom Container Apps (Backend A, Backend B) | **APIM `/mcp` endpoint per imported API** |
| Aggregator | Custom APIM aggregator API doing fan-out | **MCP-server-scoped policy** with `send-request` to Cosmos |
| Auth | Inside the MCP server | **`validate-jwt` at APIM** |
| Cosmos auth | Account key from KV | **Managed identity** via `authentication-managed-identity` |
| Container Apps count | 5 (Frontend + Backend A + Backend B + Fake Finance + Dup-Resolver) | **2 (Frontend + Dup-Resolver)** |
| Cost | ~$100 | **~$80** |

---

## How to resume in a new chat

Paste this into the new chat:

> I'm resuming work on the MCP Tool Governance V3 plan. Please read `docs/handoffs/2026-05-08.md` for the full session handoff. The source-of-truth doc is `docs/ARCHITECTURE.md`; diagrams are in `docs/ARCHITECTURE-diagrams.md`; ADRs are in `docs/adr/`. Repo split is already done. Ready to move on to PoC week 1 (extract APIM policy XML, scaffold `apim/`, `infra/terraform/`, `registry/`, `tools-cli/`, `.github/workflows/`).

That single message gives the new session everything it needs.

---

## Conventions used in v3 doc that the next session must respect

- **Don't mingle v2 and v3 content** in a single file. The user explicitly rejected that. Each version is its own standalone doc.
- **The Governance Plane (L1 + L2 + Dup-Resolver + canonical_map + election + governance allow-list) is unchanged** between v2 and v3. Only L3 implementation changed. Don't accidentally rewrite §13–§14 — they should match v2 by design (v3 §14 even cross-references v2 §14 for the worked examples to avoid duplication of the long election walk-throughs).
- **`primary` (singular) and `aliases` (plural) are the canonical_map field names.** Don't rename to `canonical` / `alternates` etc.
- **The `x-mcp-canonical-rewrite` header is the runtime governance signal.** It's stamped by the policy on alias hits and surfaced in App Insights traces + the eval harness's "Canonical rewrite hit rate" metric.
- **Naming standard is `domain.entity.action`** (canonical_id) → `domain_entity_action` (runtime_name). Regex: `^[a-z][a-z0-9_]{2,63}$`.
- **No emojis in code/docs unless the user asks** — but the v3 §4.1 evaluation table uses 🔴🟡🟢 traffic-light glyphs intentionally for visual scan. Keep them in that one table.

---

*End of handoff. Good luck, future-self.*
