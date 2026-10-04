#!/usr/bin/env bash
# start-all.sh — bring up the full MCP Tool Governance demo stack:
#   1. finance-fakes FastAPI backend  (127.0.0.1:8010)
#   2. ngrok tunnel                   (public https URL → :8010)
#   3. update APIM service-url        (both finance-api-* APIs)
#   4. dup-resolver FastAPI           (127.0.0.1:8089)
#   5. Streamlit frontend             (127.0.0.1:8501)
#
# Designed to be idempotent: kills any prior instance of each component
# before relaunching. Logs go to /tmp/<component>.log.
#
# Usage:
#   ./scripts/start-all.sh             # bring everything up
#   ./scripts/start-all.sh --no-apim   # skip the APIM service-url update
#   ./scripts/start-all.sh --no-cosmos # skip the Cosmos firewall+seed step
#
set -euo pipefail

# Force all child processes (streamlit, dup-resolver, finance-fakes) to bypass
# the ~/bin/az caching wrapper for token requests. The wrapper had multiple
# bugs that broke AOAI/Cosmos auth during demos (stale tokens, stderr
# pollution, race conditions on concurrent calls). For demo stability we
# always go straight to the real az for fresh tokens. See docs/lessons.md
# (2026-06-12 — caching az wrapper served stale tokens).
export AZ_NO_TOKEN_CACHE=1

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT=8010
RESOLVER_PORT=8089
FRONTEND_PORT=8501
APIM_NAME="apimopenai992"
APIM_RG="rg_apim"
APIM_APIS=(finance-api-governed finance-api-messy-anti-pattern-reference)

SKIP_APIM=0
SKIP_COSMOS=0
for arg in "$@"; do
  case "$arg" in
    --no-apim)   SKIP_APIM=1 ;;
    --no-cosmos) SKIP_COSMOS=1 ;;
    *) ;;
  esac
done

log() { printf "\033[1;36m[start-all]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[start-all]\033[0m %s\n" "$*" >&2; }
die() { printf "\033[1;31m[start-all]\033[0m %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. preflight
# ---------------------------------------------------------------------------
command -v ngrok >/dev/null || die "ngrok not on PATH (snap install ngrok)"
command -v az >/dev/null    || die "az CLI not on PATH"

# Belt-and-suspenders: clear any stale cached AAD tokens from prior shells
# that didn't have AZ_NO_TOKEN_CACHE=1 set. (Children of this script are
# already protected by the export above.)
rm -f /tmp/.az-token-cache.json 2>/dev/null || true
rm -rf /tmp/.az-token-cache.d 2>/dev/null  || true

[[ -d "$REPO/apps/finance-fakes/.venv"   ]] || die "missing $REPO/apps/finance-fakes/.venv"
[[ -d "$REPO/apps/dup-resolver/.venv"    ]] || die "missing $REPO/apps/dup-resolver/.venv"
[[ -d "$REPO/frontend/.venv"             ]] || die "missing $REPO/frontend/.venv"

# Restore /tmp key files from persistent store if they got cleared (reboot etc.)
# These are only used as a fallback — the .env files now hold inline keys.
if [[ -x "$REPO/scripts/load-keys.sh" ]]; then
  "$REPO/scripts/load-keys.sh" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------------------
# 0b. Azure auth preflight.
# The dup-resolver, the Streamlit agent, and the Cosmos seed all use
# DefaultAzureCredential (AAD). If 'az login' is missing or the ~/bin/az
# wrapper can't mint tokens, services start but silently fail auth — this bit
# us hard: the dup-resolver returned 500s and the L3 alias lookup 404'd. Fail
# fast here with a clear message, and warm the tokens so the first request is
# not slow. (Cosmos local/key auth is disabled by policy, so AAD is required.)
# ---------------------------------------------------------------------------
az account show >/dev/null 2>&1 || die "not logged in to Azure — run: az login"
for res in https://cognitiveservices.azure.com https://cosmos.azure.com; do
  az account get-access-token --resource "$res" --query expiresOn -o tsv >/dev/null 2>&1 \
    || die "az cannot mint a token for $res — run 'az login' (and check the ~/bin/az wrapper)"
done
log "azure auth ✓ ($(az account show --query user.name -o tsv 2>/dev/null))"

# ---------------------------------------------------------------------------
# 0c. Ensure the governed Cosmos account is reachable + seeded.
# Handles the MCAPS 'disable public network access' org policy (sets the
# SecurityControl=Ignore exclusion tag, then allowlists this machine + APIM
# egress) and seeds the canonical_map so L2 similarity + L3 alias rewrite
# work. Idempotent: only issues the slow control-plane update when the
# current network state does not already match.
# ---------------------------------------------------------------------------
if [[ "$SKIP_COSMOS" -eq 0 ]]; then
  APIM_NAME="$APIM_NAME" APIM_RG="$APIM_RG" "$REPO/scripts/ensure-cosmos.sh" \
    || die "ensure-cosmos.sh failed (see message above)"
else
  log "skipping Cosmos ensure/seed (--no-cosmos)"
fi

# ---------------------------------------------------------------------------
# 1. finance-fakes
# ---------------------------------------------------------------------------
log "stopping any prior finance-fakes / ngrok / dup-resolver / streamlit"
pkill -f "uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT"  2>/dev/null || true
pkill -f "uvicorn main:app --host 127.0.0.1 --port $RESOLVER_PORT" 2>/dev/null || true
pkill -f "streamlit run app.py"  2>/dev/null || true
pkill -f "ngrok http $BACKEND_PORT" 2>/dev/null || true
sleep 2

log "starting finance-fakes on :$BACKEND_PORT"
cd "$REPO/apps/finance-fakes"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
  > /tmp/finance-fakes.log 2>&1 & disown
deactivate
for i in {1..15}; do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/openapi-governed.json" >/dev/null 2>&1; then
    log "  finance-fakes ✓"
    break
  fi
  sleep 1
  [[ $i -eq 15 ]] && die "finance-fakes failed to start (see /tmp/finance-fakes.log)"
done

# ---------------------------------------------------------------------------
# 2. ngrok
# ---------------------------------------------------------------------------
log "starting ngrok → :$BACKEND_PORT"
nohup ngrok http "$BACKEND_PORT" --log=stdout > /tmp/ngrok.log 2>&1 & disown
NGROK_URL=""
for i in {1..20}; do
  NGROK_URL=$(curl -fsS http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
    for t in d.get('tunnels',[]):
        if t.get('proto')=='https':
            print(t['public_url']); break
except Exception:
    pass" 2>/dev/null) || NGROK_URL=""
  [[ -n "$NGROK_URL" ]] && break
  sleep 1
done
[[ -n "$NGROK_URL" ]] || die "ngrok tunnel did not come up (see /tmp/ngrok.log)"
log "  ngrok URL: $NGROK_URL"

# sanity: backend reachable via tunnel
if ! curl -fsS "$NGROK_URL/openapi-governed.json" >/dev/null 2>&1; then
  warn "tunnel returned non-200 for /openapi-governed.json (continuing anyway)"
fi

# Persist for downstream consumers / debugging
echo "$NGROK_URL" > "$REPO/.ngrok-url"

# ---------------------------------------------------------------------------
# 3. APIM service-url update
# ---------------------------------------------------------------------------
if [[ "$SKIP_APIM" -eq 0 ]]; then
  log "updating APIM service-url on ${#APIM_APIS[@]} API(s)"
  for api in "${APIM_APIS[@]}"; do
    if az apim api update --service-name "$APIM_NAME" --resource-group "$APIM_RG" \
         --api-id "$api" --service-url "${NGROK_URL}/" -o none 2>/dev/null; then
      log "  ✓ $api → $NGROK_URL/"
    else
      warn "  ✗ $api update failed (check 'az login' and corp proxy)"
    fi
  done
else
  log "skipping APIM update (--no-apim)"
fi

# ---------------------------------------------------------------------------
# 4. dup-resolver
# ---------------------------------------------------------------------------
log "starting dup-resolver on :$RESOLVER_PORT"
cd "$REPO/apps/dup-resolver"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup uvicorn main:app --host 127.0.0.1 --port "$RESOLVER_PORT" \
  > /tmp/dup-resolver.log 2>&1 & disown
deactivate
for i in {1..15}; do
  if curl -fsS "http://127.0.0.1:$RESOLVER_PORT/healthz" 2>/dev/null | grep -q '"ok":true'; then
    log "  dup-resolver ✓"
    break
  fi
  sleep 1
  [[ $i -eq 15 ]] && warn "dup-resolver healthz never returned ok=true (see /tmp/dup-resolver.log) — continuing"
done

# ---------------------------------------------------------------------------
# 5. Streamlit
# ---------------------------------------------------------------------------
log "starting Streamlit on :$FRONTEND_PORT"
cd "$REPO/frontend"
# shellcheck disable=SC1091
source .venv/bin/activate
nohup streamlit run app.py \
  --server.headless true \
  --server.port "$FRONTEND_PORT" \
  --browser.gatherUsageStats false \
  > /tmp/streamlit.log 2>&1 & disown
deactivate
for i in {1..15}; do
  if curl -fsS -o /dev/null "http://127.0.0.1:$FRONTEND_PORT/_stcore/health"; then
    log "  streamlit ✓"
    break
  fi
  sleep 1
  [[ $i -eq 15 ]] && die "streamlit failed to start (see /tmp/streamlit.log)"
done

# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------
cat <<EOF

\033[1;32m✓ All services up\033[0m
  UI         http://localhost:$FRONTEND_PORT
  Resolver   http://127.0.0.1:$RESOLVER_PORT/healthz
  Backend    http://127.0.0.1:$BACKEND_PORT/docs
  ngrok      $NGROK_URL   (also in $REPO/.ngrok-url)
  ngrok ui   http://127.0.0.1:4040

  Logs:      /tmp/finance-fakes.log  /tmp/ngrok.log  /tmp/dup-resolver.log  /tmp/streamlit.log
  Stop:      $REPO/scripts/stop-all.sh
EOF
