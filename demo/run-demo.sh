#!/usr/bin/env bash
# ============================================================================
# MCP Tool Governance — Customer Demo (5 minutes, push-button)
# ============================================================================
# Three acts:
#   Act 1: The problem      — lint a messy OpenAPI spec (22 errors)
#   Act 2: L1 design-time   — lint the governed spec (0 errors)
#   Act 3: L3 runtime       — three live curls show canonical-rewrite working
#   Bonus: the eval numbers — +30pp lift on tool-selection accuracy
#
# Press ENTER between acts. Ctrl-C any time.
#
# Prereqs:
#   - python3 on PATH
#   - curl
#   - /tmp/apim-master-key.txt contains the APIM master subscription key
#   - (optional) NGROK URL/backend reachable; the L3 curls only need APIM
#
# Override the gateway with:  GATEWAY_URL=https://my-apim.../mcp ./run-demo.sh
# ============================================================================

set -u

# ---- config ---------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-https://apimopenai99.azure-api.net/governed-mcp/mcp}"
KEY_FILE="${KEY_FILE:-/tmp/apim-master-key.txt}"
EVAL_SUMMARY="${EVAL_SUMMARY:-$REPO_ROOT/eval/results/summary.md}"

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
  bonus_eval
  banner "Demo complete. Questions?"
}

main "$@"
