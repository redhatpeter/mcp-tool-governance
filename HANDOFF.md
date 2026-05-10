# MCP Tool Governance — Session Handoff (root pointer)

**Updated:** 2026-05-10
**Purpose:** A single, always-current TL;DR for resuming work in a fresh chat.
For the full per-session log, see [`docs/handoffs/`](docs/handoffs/) — one
dated file per session.

---

## TL;DR — current state

- **L1 (design-time lint) shipped.** `tools-cli/lint.py` + workflow
  [`validate-mcp-tools.yml`](.github/workflows/validate-mcp-tools.yml). Runs
  on every PR. Stdlib-only Python; 6 rules covering wire-name collisions,
  approved-domain prefix, approved-verb action, version markers, missing
  descriptions, and disambiguation guidance.
- **L2 (similarity CI gate) shipped.** `apps/dup-resolver/check_pr.py` +
  workflow [`similarity-check.yml`](.github/workflows/similarity-check.yml).
  Runs against live Azure OpenAI (`text-embedding-3-large`, 3072 dims)
  and Azure AI Search (`mcp-tool-fingerprints`, 21 docs). Posts a markdown
  verdict back to the PR. Threshold = repo variable `CLUSTER_THRESHOLD`,
  this repo overrides to `0.92`.
- **L2 index hygiene shipped.** [`ingest-on-merge.yml`](.github/workflows/ingest-on-merge.yml)
  re-embeds + reconciles (Option A) on every push to `main`. First live
  run dropped 8 stale camelCase ghost docs.
- **L3 (runtime canonical rewrite) — smoke build live.** Three aliases
  (`financeQuoteGet`, `get_finance_quote`, `fetch_quote`) rewrite at
  `apim/policies/canonical-rewrite-smoke.policy.xml` on
  `apimopenai99.azure-api.net/governed-mcp/mcp`.
- **5-minute customer demo runnable end-to-end.** [`demo/run-demo.sh`](demo/run-demo.sh)
  + [`demo/README.md`](demo/README.md) narrator notes + captured
  [`docs/samples/demo-transcript.md`](docs/samples/demo-transcript.md)
  fallback. Acts 1–4 + Bonus eval numbers.
- **Eval harness** in `eval/` shows +30pp accuracy lift
  (governed 90% vs messy 60%, same model + prompts).

## Source-of-truth docs

| Doc | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design + 3-week PoC plan (26 sections). |
| [`docs/ARCHITECTURE-diagrams.md`](docs/ARCHITECTURE-diagrams.md) | Mermaid + draw.io. |
| [`docs/adr/`](docs/adr/) | ADRs (APIM-MCP native, repo split, topology upgrade path). |
| [`docs/lessons.md`](docs/lessons.md) | Running lessons-learned log. |
| [`docs/todo.md`](docs/todo.md) | Open work — P0 (OIDC, deferred), P1, P2, P3. |
| [`docs/handoffs/`](docs/handoffs/) | Per-session detailed handoffs. Latest: [2026-05-10](docs/handoffs/2026-05-10.md). |

## Open work (top-of-mind)

- **P0 deferred:** OIDC migration for CI → Azure (currently using key auth;
  Azure Policy `CognitiveServices_LocalAuth_Modify` will eventually re-disable
  keys, breaking the gate).
- **P1:** cold-start budget docs, daily cron `ingest.py` backup, freshness
  alert when oldest top-hit > 24h.
- **P2:** threshold sweep + top-3 nearest in PR comment.
- **P3:** L3 full implementation (beyond smoke), precision/recall study,
  spec-source plurality manifest.

Full list with rationale lives in [`docs/todo.md`](docs/todo.md).

## How to resume in a new chat

> I'm resuming work on the MCP Tool Governance PoC. Read `HANDOFF.md` for the
> current state, `docs/handoffs/2026-05-10.md` for the latest session detail,
> and `docs/todo.md` for open work. Source-of-truth design lives in
> `docs/ARCHITECTURE.md`. L1 + L2 are shipped; L3 is at smoke-build stage.
