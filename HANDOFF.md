# MCP Tool Governance — Session Handoff (root pointer)

**Updated:** 2026-05-10
**Purpose:** A single, always-current TL;DR for resuming work in a fresh chat.
For the full per-session log, see [`docs/handoffs/`](docs/handoffs/) — one
dated file per session.

---

## TL;DR — current state

**PoC complete; all three layers shipped and live on `apimopenai99`.**

- **L1 (design-time lint) shipped.** `tools-cli/lint.py` + workflow
  [`validate-mcp-tools.yml`](.github/workflows/validate-mcp-tools.yml). Runs
  on every PR. Stdlib-only Python; 6 rules covering wire-name collisions,
  approved-domain prefix, approved-verb action, version markers, missing
  descriptions, and disambiguation guidance.
- **L2 (similarity CI gate) shipped — now 5-tier.**
  `apps/dup-resolver/check_pr.py` +
  [`similarity-check.yml`](.github/workflows/similarity-check.yml). Verdict
  ladder: DUPLICATE 🛑 (≥0.92) / WARN ⚠️ ([0.87,0.92)) / REVIEW 🔍
  ([0.65,0.87)) / OK ✅ / INFO ℹ️ (rename). Both thresholds env-overridable.
- **L2 index hygiene shipped.** [`ingest-on-merge.yml`](.github/workflows/ingest-on-merge.yml)
  + [`daily-ingest.yml`](.github/workflows/daily-ingest.yml) re-embed and
  reconcile AI Search **and** Cosmos `mcp-canonical-map` on every merge
  + nightly. Stale-doc cleanup on both stores.
- **L3 (runtime canonical rewrite + tools/list filter) DEPLOYED LIVE.**
  Both `governed-mcp` and `messy-mcp` carry merged
  [`canonical-rewrite.policy.xml`](apim/policies/canonical-rewrite.policy.xml)
  + [`tools-list-filter.policy.xml`](apim/policies/tools-list-filter.policy.xml).
  Live evidence (2026-05-10): `messy-mcp/tools/list` →
  `x-mcp-tools-filtered: 3` (10 of 13 tools surfaced); `messy-mcp/tools/call
  createCustomer` → `x-mcp-canonical-rewrite: createCustomer -> customerCreate`;
  `governed-mcp/tools/list` → `x-mcp-tools-filtered: 0` (clean spec, 8 tools).
- **Policy contract CI gate shipped.**
  [`policy-tests.yml`](.github/workflows/policy-tests.yml) runs 6 unit
  tests (3 wirename + 3 verdict-tier) plus 8 Cosmos replays via
  `validate_policies.py`. Latest green:
  [run 25637828620](https://github.com/redhatpeter/mcp-tool-governance/actions/runs/25637828620).
- **Precision/recall study shipped (76-pair labeled set).**
  [`docs/eval/precision-recall.md`](docs/eval/precision-recall.md):
  precision **1.000** at 0.92 (0 false positives over 43 novels); REVIEW
  band recovers ~64 % of duplicates. `combined` fingerprint variant has
  worst separability on vendor-diverse set; production stays on `baseline`.
- **5-minute customer demo runnable end-to-end** with a 2026-05-10
  addendum capturing L3 live evidence + REVIEW examples + CI gate +
  APIM-MCP caveat.
- **Eval harness** in `eval/` showed +30pp accuracy lift
  (governed 90 % vs messy 60 %, same model + prompts) on the pre-L3 data.

### Known external blocker — APIM-MCP body forwarding

APIM-MCP currently forwards only the last property of `params.arguments`
as a raw scalar to the backend (regression of `release-service-2026-03`).
Reproduces with `<base/>`-only policies. Tracked at
[Azure-Samples/AI-Gateway#315](https://github.com/Azure-Samples/AI-Gateway/issues/315);
ready-to-send drafts in [`docs/external/`](docs/external/).

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

- **External (you-action only):** post the
  [`docs/external/issue-315-comment.md`](docs/external/issue-315-comment.md)
  comment on `Azure-Samples/AI-Gateway#315` and open the
  [`docs/external/azure-support-ticket.md`](docs/external/azure-support-ticket.md)
  ticket against `apimopenai99`.
- **P0 deferred:** OIDC migration for CI → Azure (currently using key auth;
  Azure Policy `CognitiveServices_LocalAuth_Modify` will eventually re-disable
  keys, breaking the gate).
- **Optional polish (not blocking):** re-run the §19 eval harness against
  the L3-deployed state to refresh the +30pp slide; grow labeled set 76 →
  100+; add per-customer threshold calibration script.

Full list lives in [`docs/todo.md`](docs/todo.md). Post-implementation
reflections + investments needed before pilot in
[ARCHITECTURE.md §24.A](docs/ARCHITECTURE.md#24a-appendix--post-implementation-reflections-2026-05-10).

## How to resume in a new chat

> I'm resuming work on the MCP Tool Governance PoC. Read `HANDOFF.md` for
> the current state, `docs/handoffs/2026-05-10.md` for the latest session
> detail (PM addendum), and `docs/todo.md` for open work. Source-of-truth
> design lives in `docs/ARCHITECTURE.md` (see §24.A for post-impl notes).
> All three layers are shipped + live; remaining work is external
> (#315 comment + Azure Support ticket) plus optional polish.
