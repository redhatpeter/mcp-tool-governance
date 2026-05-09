# Customer Demo — Narrator Notes

A 5-minute push-button walkthrough of the MCP Tool Governance PoC. Run [`run-demo.sh`](run-demo.sh) and read these notes between acts.

---

## Quickstart

```bash
# From repo root:
chmod +x demo/run-demo.sh           # one time
./demo/run-demo.sh                  # interactive (pauses for ENTER)
AUTO=1 ./demo/run-demo.sh           # non-stop run (for recording)
```

Override the gateway if demoing against a different APIM:
```bash
GATEWAY_URL=https://my-apim.azure-api.net/governed-mcp/mcp ./demo/run-demo.sh
```

Act 4 (L2 semantic dedup) needs the dup-resolver running. Optional — Act 4 falls back to captured `docs/samples/*.json` if the resolver isn't reachable:
```bash
cd apps/dup-resolver && source .venv/bin/activate \
  && uvicorn main:app --host 127.0.0.1 --port 8089 &
```

---

## Prereqs (one-time)

| Item | Where | Notes |
|---|---|---|
| `python3` | PATH | stdlib only, no pip installs needed for the demo itself |
| `curl` | PATH | any version |
| `/tmp/apim-master-key.txt` | local file | APIM master subscription key (raw, no whitespace). Get from Portal → APIM → Subscriptions → built-in all-access |
| Gateway reachable | network | `https://apimopenai99.azure-api.net/governed-mcp/mcp` by default |
| ngrok backend | optional | only needed if you want Act 3 to actually return a 200 body. Headers (which is what we read) come back regardless |
| dup-resolver running | optional | Act 4 needs `http://127.0.0.1:8089` reachable. If it isn't, Act 4 falls back to captured samples in `docs/samples/`. |

---

## What to say between acts

### Before you start (15 sec)
> "There's a gap between what teams *ship* to MCP and what an LLM can *actually use*. We see it every day — duplicate tools, drifted names, no descriptions. This demo shows three layers of governance that close that gap, all on top of stock Azure API Management."

### Act 1 — The Problem (45 sec)
**Narrator beats while the lint output streams:**
- *"Real-world MCP surfaces look like this. 8 operations, 22 errors."*
- Point at an **E003** line: *"Two operations both produce wire name `createCustomer` — APIM-MCP silently keeps one and drops the other. The LLM never even sees the second one."*
- Point at a **W101** line: *"No description. The model has to guess what this tool does from the name alone — that's how you get hallucinated tool calls."*
- Point at an **E006** line: *"`...V2`, `...legacy` — that's version drift baked into the tool name. Version belongs in the API spec, not the tool ID."*
- Close: *"This is failure mode #1 through #5 from the architecture doc, all caught by one design-time check."*

### Act 2 — Layer 1 (30 sec)
**Narrator beats:**
- *"Same lint, same 8 operations — but on the curated `governed` spec. Zero errors, zero warnings."*
- *"This runs on every PR via GitHub Actions — `validate-mcp-tools.yml`. Bad tools never reach production. That's L1."*
- (If asked) *"Stdlib only Python — no dependencies. Easy to drop into any CI."*

### Act 3 — Layer 3 (90 sec — the headline)
**Setup beat:**
- *"L1 catches what *we* author. But you can't force every caller to use the canonical name — legacy clients, federated tools from Bedrock or Vertex, copy-pasted SDK examples, even LLM hallucinations. L3 fixes that at the gateway."*

**Three test calls — what to point at on screen:**

| Test | Pre-rewrite name | Header you'll see | What to say |
|---|---|---|---|
| **A** | `financeQuoteGet` | `x-mcp-canonical-rewrite: none (financeQuoteGet)` | *"Already canonical — gateway is a no-op. Proves we don't break the happy path."* |
| **B** | `get_finance_quote` | `x-mcp-canonical-rewrite: get_finance_quote -> financeQuoteGet` | *"Legacy snake_case caller. Gateway looks up Cosmos, rewrites the JSON-RPC body, executes the canonical tool. Caller never knows."* |
| **C** | `fetch_quote` | `x-mcp-canonical-rewrite: fetch_quote -> financeQuoteGet` | *"Different team's naming convention — same canonical underneath. This is how you onboard a federated tool catalog without breaking anyone."* |

**Architecture call-outs (use whichever land):**
- *"Cosmos auth is **managed identity** — no keys in the policy, no keys in Key Vault."*
- *"Lookup is **cached 60s in APIM** — Cosmos hit only on the first call per name."*
- *"**Fail open** — if Cosmos is unreachable, the request goes through unrewritten. We never break the call path for a metadata lookup."*
- *"All this is **one APIM policy** — ~80 lines of XML. No new services, no sidecars, no application-code changes."*

### Act 4 — Layer 2 (60 sec — the data-driven dedup)
**Setup beat:**
- *"L1 catches naming drift. L3 absorbs aliases at runtime. L2 is the missing piece — what about a NEW tool that PASSES the linter but is semantically a duplicate of one we already have?"*

**`/clusters` beat:**
- *"Every tool gets embedded with `text-embedding-3-large` — 3072 dimensions — and indexed in Azure AI Search. We cluster at cosine ≥ 0.88."*
- Point at the two multi-member clusters: *"`createCustomer` and `customerCreate` — same intent, two wire names. The cluster found them. We elect a canonical deterministically."*

**`/similarity` beat (the headline):**
- *"Now imagine a PR adds `financeQuoteFetch`. Different verb, plausible-looking name, no lint error. L2 says: WARN — 0.83 against `financeQuoteGet` — reviewer confirms."*
- *"At 0.88 it'd be DUPLICATE and we fail the PR. Same code lives in `.github/workflows/similarity-check.yml`."*

**One honest caveat (only if asked):**
- *"The threshold is conservative on purpose. The cross-server messy ↔ governed pairs hit ~0.75 because messy descriptions are deliberately thin. WARN catches those at PR time, which is the realistic case."*

### Bonus — Eval numbers (30 sec — the "so what")
- *"Same model. Same 20 prompts. The only thing we changed was the tool surface."*
- Point at the +30pp number: *"30 percentage points of agent accuracy. That's the dollar value of governance."*
- *"And remember — the messy 60% wasn't catastrophically broken. It looked fine. That's the trap."*

### Closing (15 sec)
- *"Three layers, all running on stock Azure: API Management, Cosmos, GitHub Actions. No custom MCP server code to maintain."*
- *"What we're showing is the PoC. The same shape scales to multi-domain federation — that's roadmap section 4.1 of the architecture doc."*

---

## Recovery playbook (if something goes wrong)

| Symptom | Fix |
|---|---|
| `missing /tmp/apim-master-key.txt` | `az rest --method post --url ".../service/apimopenai99/subscriptions/master/listSecrets?api-version=2024-06-01-preview" --headers "Content-Length=0" --query primaryKey -o tsv > /tmp/apim-master-key.txt` |
| Act 3 returns no headers | Gateway is down OR policy was detached. Check Portal → MCP Servers → governed-mcp → Policies. Re-paste from `apim/policies/canonical-rewrite-smoke.policy.xml`. |
| Act 3 returns `502` / `504` | ngrok backend is down. Headers still appear though, which is what the demo reads. Demo continues to work. |
| Act 3 returns `404 Resource Not Found` for the alias | The alias isn't in Cosmos. Re-seed: `python3 tools-cli/seed_canonical_map.py` |
| Act 4 says "resolver not running" | Either start it (`cd apps/dup-resolver && uvicorn main:app --port 8089`) or accept the captured-sample fallback — the demo continues either way. |
| Lint says "no OpenAPI specs found" | You're not in the repo root. `cd` to repo root first. |
| Pre-recorded fallback | If Azure is unreachable entirely, walk through [`docs/samples/demo-transcript.md`](../docs/samples/demo-transcript.md) screen-share. Same script, captured output. |

---

## Demo asset inventory

- [`run-demo.sh`](run-demo.sh) — the script
- [`README.md`](README.md) — this file (narrator notes)
- [`../docs/samples/demo-transcript.md`](../docs/samples/demo-transcript.md) — pre-captured clean run, screen-share fallback
- [`../docs/samples/governed-mcp.tools-list.json`](../docs/samples/governed-mcp.tools-list.json) — current tool catalog snapshot
- [`../eval/results/summary.md`](../eval/results/summary.md) — eval numbers (the "so what" slide)
- [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) — full PoC plan, for follow-up questions

## Time budget

| Segment | Target | Cumulative |
|---|---|---|
| Intro | 0:15 | 0:15 |
| Act 1 (problem) | 0:45 | 1:00 |
| Act 2 (L1) | 0:30 | 1:30 |
| Act 3 (L3 — three curls) | 1:30 | 3:00 |
| Act 4 (L2 — clusters + similarity) | 1:00 | 4:00 |
| Bonus (eval) | 0:30 | 4:30 |
| Closing | 0:15 | 4:45 |
| Q&A buffer | 1:15 | 6:00 |
