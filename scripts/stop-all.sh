#!/usr/bin/env bash
# stop-all.sh — kill all demo processes started by start-all.sh.
# Does not touch unrelated uvicorn/streamlit instances on other ports.
#
# Usage:
#   ./scripts/stop-all.sh                 # just stop the local processes
#   ./scripts/stop-all.sh --lock-cosmos   # also re-disable Cosmos public
#                                         # network access (restore the secure
#                                         # org baseline; slow control-plane op)
set -euo pipefail

log()  { printf "\033[1;36m[stop-all]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[stop-all]\033[0m %s\n" "$*" >&2; }

LOCK_COSMOS=0
for arg in "$@"; do
  case "$arg" in
    --lock-cosmos) LOCK_COSMOS=1 ;;
    *) ;;
  esac
done

BACKEND_PORT=8010
RESOLVER_PORT=8089
COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-cosmoslab82658}"
COSMOS_RG="${COSMOS_RG:-cosmos-ws}"

log "stopping streamlit (port 8501)"
pkill -f "streamlit run app.py" 2>/dev/null || true

log "stopping dup-resolver (port $RESOLVER_PORT)"
pkill -f "uvicorn main:app --host 127.0.0.1 --port $RESOLVER_PORT" 2>/dev/null || true

log "stopping finance-fakes (port $BACKEND_PORT)"
pkill -f "uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT"  2>/dev/null || true

log "stopping ngrok (→ $BACKEND_PORT)"
pkill -f "ngrok http $BACKEND_PORT" 2>/dev/null || true

sleep 1

# Optional: restore the secure Cosmos baseline (public access disabled). Kept
# opt-in because it triggers a slow control-plane update; skip it during
# routine stop/start cycles. The org policy would eventually re-disable this
# anyway, but --lock-cosmos does it immediately. The SecurityControl=Ignore
# exclusion tag is left in place so start-all can re-enable access cleanly.
if [[ "$LOCK_COSMOS" -eq 1 ]]; then
  if command -v az >/dev/null && az account show >/dev/null 2>&1; then
    log "re-disabling Cosmos public network access ($COSMOS_ACCOUNT) — may take a few minutes"
    if az cosmosdb update -n "$COSMOS_ACCOUNT" -g "$COSMOS_RG" \
         --public-network-access DISABLED -o none 2>/dev/null; then
      log "  cosmos locked ✓ (publicNetworkAccess=Disabled)"
    else
      warn "  failed to re-disable Cosmos public access (check 'az login' / permissions)"
    fi
  else
    warn "--lock-cosmos requested but az is unavailable or not logged in — skipping"
  fi
fi

log "done"
