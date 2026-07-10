#!/usr/bin/env bash
# stop-all.sh — kill all demo processes started by start-all.sh.
# Does not touch unrelated uvicorn/streamlit instances on other ports.
set -euo pipefail

log() { printf "\033[1;36m[stop-all]\033[0m %s\n" "$*"; }

BACKEND_PORT=8010
RESOLVER_PORT=8089

log "stopping streamlit (port 8501)"
pkill -f "streamlit run app.py" 2>/dev/null || true

log "stopping dup-resolver (port $RESOLVER_PORT)"
pkill -f "uvicorn main:app --host 127.0.0.1 --port $RESOLVER_PORT" 2>/dev/null || true

log "stopping finance-fakes (port $BACKEND_PORT)"
pkill -f "uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT"  2>/dev/null || true

log "stopping ngrok (→ $BACKEND_PORT)"
pkill -f "ngrok http $BACKEND_PORT" 2>/dev/null || true

sleep 1
log "done"
