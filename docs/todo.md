# TODO

Open work items for the MCP Tool Governance POC. Grouped by priority.
Last updated: 2026-05-10 — added Option A (ingest-on-merge) + companion
PR-time deletion-aware filter as P0 items.

## P0 — operational gaps that will bite us next demo

- [ ] **`ingest-on-merge` workflow (Option A — index reconciliation)**
  Today the AI Search index drifts from `main` until someone manually
  re-runs `ingest.py`. Result: deletions and renames leave **stale ghost
  documents** that future PRs match against (Scenario 1 self-match,
  Scenario 6 deletion drift). Add `.github/workflows/ingest-on-merge.yml`
  triggered on `push` to `main` for `apim/openapi/**`. Workflow runs
  `ingest.py`, which already handles upserts; one new helper
  `reconcile_deletions(desired_ids)` computes `index_ids − desired_ids`
  and issues `delete_documents` for the difference. Re-elects canonicals
  in the same run. ~25 lines of YAML, ~10 lines of Python.
  - Solves: Scenario 6 (deletions), drift after rename merges.
  - Does NOT solve: in-flight PR-branch self-match (need PR-time
    "deletion-aware filter" — separate item below).
  - Risk: AOAI quota / write contention — add `concurrency:` guard and
    a daily cron `ingest.py` as belt-and-braces backup.

- [ ] **PR-time deletion-aware filter (rename UX)**
  Companion to `ingest-on-merge`: while a rename PR is open, the index
  still has the old name and `check_pr.py` flags the new name as a
  DUPLICATE against its own ghost. Compute `deleted_ops = base_ops −
  head_ops` per spec; if a hit's `tool_name` is in that set on the same
  `server`, downgrade verdict from DUPLICATE → INFO ("looks like a
  rename — confirmed by deletion"). Avoids the rename foot-gun without
  waiting for the post-merge re-ingest.

- [ ] **OIDC migration for CI → Azure**
  Currently CI uses `AOAI_API_KEY` + `SEARCH_ADMIN_KEY` repo secrets. Azure
  Policy `CognitiveServices_LocalAuth_Modify` will eventually re-disable key
  auth on `common-open-ai`, breaking the gate. Migrate to GitHub OIDC →
  federated credential → AAD-only auth (`DefaultAzureCredential` already
  supported in `apps/dup-resolver/config.py`).

- [ ] **Decide canonical CLUSTER_THRESHOLD**
  Repo variable currently overrides `config.py` default (0.88) to 0.92.
  Either bake 0.92 into `config.py` and remove the repo variable, or
  document 0.88 as the "ship default" and 0.92 as the "tightened org
  override" in `apps/dup-resolver/README.md`.

- [ ] **Close or document PR #1**
  https://github.com/redhatpeter/mcp-tool-governance/pull/1 is the
  validation artifact for the L2 gate (DUPLICATE 0.958, red ❌). Either
  close it as a "do not merge — validation only" smoke test, or keep it
  open as a permanent demo artifact and pin it.

## P1 — gaps surfaced by the test sweep

- [ ] **Multi-file PR handling**
  Test harness only exercises single-file PRs. Workflow `mapfile` with
  `git diff --name-only ... 'apim/openapi/*.json'` should handle 2+ specs
  changed in one PR but is unverified end-to-end. Add a scenario.

- [ ] **Index freshness signal in the verdict**
  Even with `ingest-on-merge`, there's a window where a PR's verdict was
  computed against an older index snapshot. Surface `last_seen_utc` of
  the top hit (and the index-wide max) in the markdown report so
  reviewers can tell when their verdict was computed and whether a
  re-run might change it.

- [ ] **CI cold-start budget**
  Local script-cold elapsed: 1 op = 6.7s, 5 = 7.6s, 20 = 12.1s. CI runner
  spin-up adds ~30s on top. Document expected end-to-end CI time in
  `apps/dup-resolver/README.md` so reviewers know what "normal" looks like.

- [ ] **Self-match filtering for renames**
  Test #5 confirmed renaming an op (`financeQuoteGet` → `getQuote`) flags
  as DUPLICATE against its own indexed fingerprint (score 0.928). That's
  technically correct but noisy for legitimate renames. Consider filtering
  hits where `tool_name` matches a deleted op in the same PR.

## P2 — polish

- [ ] **Deprecation warning: Node.js 20 actions**
  GitHub annotation on every run: `actions/checkout@v4` and
  `actions/setup-python@v5` use Node 20. Bump when v5 / v6 ships with
  Node 24 support, or set `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`.

- [ ] **Threshold sweep in CI as a comment**
  Today the sweep runs only in the local harness. Optionally post the
  sweep table as a PR comment so reviewers can see how the verdict would
  shift at 0.85 / 0.92 / 0.96 for borderline cases.

- [ ] **Capture a fresh demo transcript at 0.92**
  `docs/samples/demo-transcript.md` Act 4 still shows the original 0.832
  WARN verdict from the captured sample. With the live PR now scoring
  0.958 DUPLICATE at 0.92, refresh the transcript so the README and the
  live system agree.

## P3 — exploration / future work

- [ ] **Bonus: PR comment with top-3 nearest neighbors**
  Verdict markdown table only shows the top match. Adding the second and
  third nearest hits would help reviewers spot when a "DUPLICATE" is
  actually a near-tie between two candidates.

- [ ] **MCP-side enforcement (L3)**
  L1 (lint) and L2 (similarity CI) are design-time. L3 — runtime
  enforcement via the MCP gateway / APIM policy — is sketched in
  `docs/ARCHITECTURE.md` §3.4 but not implemented.

- [ ] **Quantitative precision/recall study**
  Build a labeled set of 30–50 known-duplicate vs known-novel pairs from
  real-world MCP servers and report precision/recall per threshold. Would
  let us defend the 0.88 vs 0.92 choice with a number, not a vibe.
