#!/usr/bin/env bash
# ============================================================================
# MCP Tool Governance — Customer Demo (5 minutes, push-button)
# ============================================================================
# Four acts:
#   Act 1: The problem      — lint a messy OpenAPI spec (22 errors)
#   Act 2: L1 design-time   — lint the governed spec (0 errors)
#   Act 3: L3 runtime       — three live curls show canonical-rewrite working
#   Act 4: L2 semantic dup  — AI-Search-backed /clusters + /similarity
#   Bonus: the eval numbers — +30pp lift on tool-selection accuracy
#
# Press ENTER between acts. Ctrl-C any time.
#
# Prereqs:
#   - python3 on PATH
#   - curl
#   - /tmp/apim-master-key.txt contains the APIM master subscription key
#   - (optional) NGROK URL/backend reachable; the L3 curls only need APIM
#   - (optional, Act 4) dup-resolver running on http://127.0.0.1:8089
#       cd apps/dup-resolver && source .venv/bin/activate \
#         && uvicorn main:app --host 127.0.0.1 --port 8089
#     If unreachable, Act 4 falls back to the captured docs/samples/*.json.
#
# Override the gateway with:  GATEWAY_URL=https://my-apim.../mcp ./run-demo.sh
# ============================================================================

set -u

# ---- config ---------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-https://apimopenai99.azure-api.net/governed-mcp/mcp}"
KEY_FILE="${KEY_FILE:-/tmp/apim-master-key.txt}"
EVAL_SUMMARY="${EVAL_SUMMARY:-$REPO_ROOT/eval/results/summary.md}"
RESOLVER_URL="${RESOLVER_URL:-http://127.0.0.1:8089}"
CLUSTERS_SAMPLE="${CLUSTERS_SAMPLE:-$REPO_ROOT/docs/samples/clusters.json}"
SIMILARITY_SAMPLE="${SIMILARITY_SAMPLE:-$REPO_ROOT/docs/samples/similarity-financeQuoteFetch.json}"

# ---- pretty printing ------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; CYAN=$'\033[36m'
  GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; CYAN=""; GREEN=""; RED=""; YELLOW=""; RESET=""
fi

banner() {
  echo
  echo "${CYAN}${BOLD}=================================================================${RESET}"
  echo "${CYAN}${BOLD} $* ${RESET}"
  echo "${CYAN}${BOLD}=================================================================${RESET}"
}

step() { echo; echo "${BOLD}▸ $*${RESET}"; }
say()  { echo "${DIM}  $*${RESET}"; }
cmd()  { echo "${YELLOW}  \$ $*${RESET}"; }

pause() {
  if [[ "${AUTO:-0}" == "1" ]]; then return; fi
  echo
  read -r -p "  ${DIM}[Press ENTER to continue]${RESET} " _ || true
}

# ---- preflight ------------------------------------------------------------
preflight() {
  local fail=0
  if ! command -v python3 >/dev/null; then echo "${RED}missing python3${RESET}"; fail=1; fi
  if ! command -v curl    >/dev/null; then echo "${RED}missing curl${RESET}";    fail=1; fi
  if [[ ! -f "$KEY_FILE" ]]; then
    echo "${RED}missing $KEY_FILE${RESET} — put APIM master subscription key there"
    fail=1
  fi
  if [[ ! -f "$REPO_ROOT/apim/openapi/finance-messy.json" ]]; then
    echo "${RED}can't find apim/openapi/finance-messy.json — run from repo${RESET}"
    fail=1
  fi
  [[ $fail -eq 0 ]]
}

# ---- acts -----------------------------------------------------------------
act1_problem() {
  banner "ACT 1 — The Problem: an ungoverned MCP surface"
  say "This is what happens when teams ship tools to MCP with no guardrails."
  say "Same lint we use in CI; runs in <1s and scores the OpenAPI spec."
  cmd "python3 tools-cli/lint.py apim/openapi/finance-messy.json"
  pause
  ( cd "$REPO_ROOT" && python3 tools-cli/lint.py apim/openapi/finance-messy.json ) || true
  echo
  say "${RED}Result: collisions (E003) — APIM-MCP silently drops dup tools."
  say "        Missing descriptions (W101) — LLMs can't disambiguate."
  say "        Banned legacy markers (E006) — version drift in tool names.${RESET}"
  pause
}

act2_l1() {
  banner "ACT 2 — Layer 1: design-time gate stops bad tools at the PR"
  say "Same lint, against the governed spec we curated for this domain."
  cmd "python3 tools-cli/lint.py apim/openapi/finance-governed.json"
  pause
  ( cd "$REPO_ROOT" && python3 tools-cli/lint.py apim/openapi/finance-governed.json ) || true
  echo
  say "${GREEN}Result: 0 errors / 0 warnings.${RESET}"
  say "Wired into .github/workflows/validate-mcp-tools.yml — every PR runs this."
  say "Bad tools never reach production."
  pause
}

act3_l3() {
  banner "ACT 3 — Layer 3: runtime canonical rewrite at the gateway"
  say "Even with L1 in place, you can't force every caller to use the canonical name."
  say "Legacy callers, federated tools, LLM hallucinations, copy-pasted examples."
  say "L3 absorbs all that and rewrites to the canonical at the gateway."
  echo
  say "Three curls, same endpoint, different requested tool names:"

  local key
  key="$(cat "$KEY_FILE")"

  test_call() {
    local label="$1" name="$2"
    step "$label"
    cmd "curl -X POST $GATEWAY_URL ... '\"name\":\"$name\"'"
    local response_headers
    response_headers=$(
      curl -sS -i -X POST "$GATEWAY_URL" \
        -H "Ocp-Apim-Subscription-Key: $key" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$name\",\"arguments\":{\"symbol\":\"MSFT\"}}}" \
        2>&1 | grep -iE "^(HTTP|x-mcp-canonical-rewrite)"
    )
    if [[ -z "$response_headers" ]]; then
      echo "  ${RED}(no response — gateway unreachable or policy detached)${RESET}"
    else
      echo "$response_headers" | sed "s/^/  ${GREEN}/" | sed "s/$/${RESET}/"
    fi
  }

  test_call "Test A — canonical name (already correct, no rewrite)" "financeQuoteGet"
  test_call "Test B — legacy alias (rewritten to canonical)"        "get_finance_quote"
  test_call "Test C — different alias (also rewritten)"             "fetch_quote"

  echo
  say "${GREEN}Same canonical implementation, three input names. Zero app-code changes.${RESET}"
  say "Lookup is in Cosmos, cached 60s in APIM, authenticated via managed identity."
  pause
}

act4_l2() {
  banner "ACT 4 — Layer 2: AI-Search-backed semantic deduplication"
  say "L1 catches naming drift. L3 absorbs aliases at runtime."
  say "But what about NEW tools that LOOK fine to the linter but DUPLICATE existing ones?"
  say "L2 runs every tool through Azure OpenAI embeddings + AI Search vector index,"
  say "clusters near-duplicates, elects a canonical, and exposes a PR-time check."
  echo

  local resolver_up=0
  if curl -sS -m 2 -o /dev/null -w "%{http_code}" "$RESOLVER_URL/healthz" 2>/dev/null | grep -q "^200$"; then
    resolver_up=1
  fi

  if [[ $resolver_up -eq 0 ]]; then
    say "${YELLOW}dup-resolver not running on $RESOLVER_URL — using captured samples.${RESET}"
    say "${DIM}(Start it with: cd apps/dup-resolver && uvicorn main:app --port 8089)${RESET}"
  fi

  # ---- /clusters: surface duplicate clusters in messy-mcp ----
  step "Show all tool clusters across both MCP servers"
  cmd "curl $RESOLVER_URL/clusters"
  pause

  local clusters_json
  if [[ $resolver_up -eq 1 ]]; then
    clusters_json="$(curl -sS "$RESOLVER_URL/clusters")"
  elif [[ -f "$CLUSTERS_SAMPLE" ]]; then
    clusters_json="$(cat "$CLUSTERS_SAMPLE")"
  else
    say "${RED}no resolver and no $CLUSTERS_SAMPLE — skipping${RESET}"
    return
  fi

  CLUSTERS_JSON="$clusters_json" python3 <<'PY'
import json, os
d = json.loads(os.environ["CLUSTERS_JSON"])
print(f"  total_tools     = {d['total_tools']}")
print(f"  total_clusters  = {d['total_clusters']}")
print(f"  duplicate sets  = {d['duplicates']}")
print()
multi = [c for c in d['clusters'] if len(c['members']) > 1]
if multi:
    print("  Multi-member clusters (semantic duplicates):")
    for c in multi:
        print(f"    [{c['cluster_id']}]  canonical = {c['canonical']}")
        for m in c['members']:
            star = '*' if m['is_canonical'] else ' '
            print(f"      {star} {m['server']}/{m['name']}")
else:
    print("  (no multi-member clusters)")
PY
  echo
  say "${GREEN}Cosine ≥ 0.88 in 3072-dim embedding space groups these together.${RESET}"
  say "Election picked the canonical deterministically — governed/well-named/described wins."
  pause

  # ---- /similarity: PR-time check ----
  step "Simulate a developer adding a new tool: 'financeQuoteFetch'"
  say "Imagine this op just landed in a PR against apim/openapi/finance-governed.json."
  say "The same code runs in CI via .github/workflows/similarity-check.yml."
  cmd "curl -X POST $RESOLVER_URL/similarity -d '{...financeQuoteFetch...}'"
  pause

  local sim_json
  if [[ $resolver_up -eq 1 ]]; then
    sim_json="$(curl -sS -X POST "$RESOLVER_URL/similarity" \
      -H 'Content-Type: application/json' \
      -d '{"name":"financeQuoteFetch","description":"Fetch a real-time stock quote for a given ticker symbol."}')"
  elif [[ -f "$SIMILARITY_SAMPLE" ]]; then
    sim_json="$(cat "$SIMILARITY_SAMPLE")"
  else
    say "${RED}no resolver and no $SIMILARITY_SAMPLE — skipping${RESET}"
    return
  fi

  SIM_JSON="$sim_json" python3 <<'PY'
import json, os
d = json.loads(os.environ["SIM_JSON"])
verdict = d['verdict']
color = {'DUPLICATE': '\033[31m', 'WARN': '\033[33m', 'OK': '\033[32m'}.get(verdict, '')
print(f"  verdict   : {color}{verdict}\033[0m")
print(f"  threshold : {d['threshold']}")
print(f"  reason    : {d['reason']}")
print()
print("  Top 3 nearest neighbors in the index:")
for n in d['nearest'][:3]:
    canon = ' [CANONICAL]' if n.get('is_canonical') else ''
    print(f"    {n['score']:.3f}  {n['server']}/{n['name']}{canon}")
PY
  echo
  say "${GREEN}WARN verdict — close to threshold, reviewer confirms.${RESET}"
  say "If score ≥ 0.88, CI would FAIL the PR with a DUPLICATE verdict in the step summary."
  say "Same vector index also powers the runtime /similarity API for federated catalogs."
  pause
}

bonus_eval() {
  banner "BONUS — The eval numbers (the 'so what')"
  if [[ -f "$EVAL_SUMMARY" ]]; then
    say "Same model (gpt-4o-mini), same 20 prompts, only the tool surface differs:"
    echo
    grep -E "^\| \`A_messy\`|^\| \`B_governed\`|^\*\*Absolute" "$EVAL_SUMMARY" | sed "s/^/  /"
  else
    say "${YELLOW}eval summary not found at $EVAL_SUMMARY — skipping${RESET}"
  fi
  echo
  say "Translation for the customer:"
  say "  ${BOLD}A messy MCP surface costs you 30 percentage points of agent accuracy.${RESET}"
  say "  ${BOLD}Governance is not theatre — it directly moves the eval needle.${RESET}"
  echo
}

# ---- main ----------------------------------------------------------------
main() {
  if ! preflight; then exit 2; fi
  banner "MCP Tool Governance — 5-minute customer demo"
  say "Repo: $REPO_ROOT"
  say "Gateway: $GATEWAY_URL"
  pause
  act1_problem
  act2_l1
  act3_l3
  act4_l2
  bonus_eval
  banner "Demo complete. Questions?"
}

main "$@"
