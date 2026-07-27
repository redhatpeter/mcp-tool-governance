#!/usr/bin/env bash
# ensure-cosmos.sh — make the governed Cosmos account reachable + seeded.
#
# Why this exists (issues we hit repeatedly during demos):
#   * The subscription sits under MCAPS governance policy
#     "SFI - Disable public network access on Cosmos DB accounts", a Modify
#     effect assigned at the tenant-root management group. It force-resets
#     publicNetworkAccess=Disabled — so the portal/CLI "kept snapping back".
#     That policy has a built-in escape hatch: it skips any account (or RG)
#     carrying the tag SecurityControl=Ignore. We set that tag, then enable
#     public access restricted to just this machine + APIM's egress IP.
#   * With access disabled, both the local seed script AND APIM's runtime
#     canonical-map lookup fail -> the L3 policy fails open -> alias tools/call
#     returns 404. Allowlisting APIM's outbound IP fixes the runtime path.
#   * Cosmos local (key) auth is disabled by policy (disableLocalAuth=true),
#     so everything uses AAD (az login) — no keys involved here.
#   * The canonical_map must be seeded or aliases won't resolve.
#
# Safe to run repeatedly: it only issues the slow control-plane update when
# the current network state doesn't already match what we need.
#
# Usage:
#   ./scripts/ensure-cosmos.sh            # ensure network + seed
#   ./scripts/ensure-cosmos.sh --no-seed  # network only
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

COSMOS_ACCOUNT="${COSMOS_ACCOUNT:-cosmoslab82658}"
COSMOS_RG="${COSMOS_RG:-cosmos-ws}"
APIM_NAME="${APIM_NAME:-apimopenai99}"
APIM_RG="${APIM_RG:-Default-ActivityLogAlerts}"
TAG_NAME="${COSMOS_EXCLUSION_TAG_NAME:-SecurityControl}"
TAG_VALUE="${COSMOS_EXCLUSION_TAG_VALUE:-Ignore}"

DO_SEED=1
[[ "${1:-}" == "--no-seed" ]] && DO_SEED=0

log()  { printf "\033[1;36m[ensure-cosmos]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[ensure-cosmos]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[ensure-cosmos]\033[0m %s\n" "$*" >&2; exit 1; }

command -v az   >/dev/null || die "az CLI not on PATH"
command -v curl >/dev/null || die "curl not on PATH"

# Retry wrapper for flaky ARM calls. We saw intermittent
# "Operation returned an invalid status 'Bad Request'" when firing several
# az calls back-to-back (throttling / ~/bin/az wrapper hiccups). Retries a
# few times and prints stdout on success.
az_retry() {
  local n=0 max=4 out rc
  while :; do
    out="$("$@" 2>/tmp/ensure-cosmos.err)"; rc=$?
    if [[ $rc -eq 0 ]]; then printf '%s' "$out"; return 0; fi
    n=$((n+1)); (( n >= max )) && { cat /tmp/ensure-cosmos.err >&2; return "$rc"; }
    sleep 2
  done
}

# ---------------------------------------------------------------------------
# 0. auth preflight — everything below needs a valid az login (AAD only).
# ---------------------------------------------------------------------------
az account show >/dev/null 2>&1 || die "not logged in — run: az login"

# ---------------------------------------------------------------------------
# 1. discover the IPs that need access: this machine + APIM egress.
# ---------------------------------------------------------------------------
MYIP="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null \
        || curl -fsS --max-time 10 https://ifconfig.me 2>/dev/null || true)"
MYIP="$(printf '%s' "$MYIP" | tr -d '[:space:]')"
[[ "$MYIP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "could not detect this machine's public IP"
log "this machine public IP: $MYIP"

APIMIP="$(az_retry az apim show -n "$APIM_NAME" -g "$APIM_RG" \
          --query "publicIpAddresses[0]" -o tsv | tr -d '[:space:]')"
if [[ "$APIMIP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  log "APIM ($APIM_NAME) egress IP: $APIMIP"
else
  warn "could not resolve APIM egress IP (runtime L3 lookup may fail)"
  APIMIP=""
fi

# Desired allowlist = this machine + APIM egress (deduped, sorted).
DESIRED="$(printf '%s\n%s\n' "$MYIP" "$APIMIP" | grep -E '^[0-9.]+$' | sort -u | paste -sd, -)"

# ---------------------------------------------------------------------------
# 2. read current state — one ARM call, parsed locally (avoids throttling).
# ---------------------------------------------------------------------------
ACC_JSON="$(az_retry az cosmosdb show -n "$COSMOS_ACCOUNT" -g "$COSMOS_RG" -o json)" \
  || die "cannot read Cosmos account $COSMOS_ACCOUNT in $COSMOS_RG (check name/RG and permissions)"
_get() { printf '%s' "$ACC_JSON" | python3 -c "import sys,json;d=json.load(sys.stdin);$1"; }
CUR_PNA="$(_get "print(d.get('publicNetworkAccess',''))")"
CUR_RULES="$(_get "print(','.join(sorted(r['ipAddressOrRange'] for r in (d.get('ipRules') or []))))")"
CUR_TAG="$(_get "print((d.get('tags') or {}).get('${TAG_NAME}',''))")"
RID="$(_get "print(d.get('id',''))")"
[[ -n "$RID" ]] || die "could not read Cosmos resource id"

# ---------------------------------------------------------------------------
# 3. ensure the policy-exclusion tag (fast; must exist before enabling access,
#    otherwise the Modify policy re-disables it).
# ---------------------------------------------------------------------------
if [[ "$CUR_TAG" != "$TAG_VALUE" ]]; then
  log "adding policy-exclusion tag ${TAG_NAME}=${TAG_VALUE}"
  az_retry az tag update --resource-id "$RID" --operation merge --tags "${TAG_NAME}=${TAG_VALUE}" -o none \
    || die "failed to add exclusion tag (need Contributor on the account)"
else
  log "exclusion tag ${TAG_NAME}=${TAG_VALUE} already present"
fi

# ---------------------------------------------------------------------------
# 4. enable public access + allowlist, but only if it isn't already correct
#    (the control-plane update takes minutes — skip it when unchanged).
# ---------------------------------------------------------------------------
if [[ "$CUR_PNA" == "Enabled" && "$CUR_RULES" == "$DESIRED" ]]; then
  log "network already correct (Enabled; allowlist: ${DESIRED}) — skipping update"
else
  log "updating firewall: publicNetworkAccess=Enabled, allowlist=${DESIRED} (this can take a few minutes)"
  az_retry az cosmosdb update -n "$COSMOS_ACCOUNT" -g "$COSMOS_RG" \
    --public-network-access ENABLED --ip-range-filter "$DESIRED" -o none \
    || die "cosmosdb update failed — if publicNetworkAccess snapped back, confirm the ${TAG_NAME}=${TAG_VALUE} tag stuck"
  FINAL_PNA="$(az_retry az cosmosdb show -n "$COSMOS_ACCOUNT" -g "$COSMOS_RG" --query "publicNetworkAccess" -o tsv)"
  [[ "$FINAL_PNA" == "Enabled" ]] \
    || die "publicNetworkAccess is still '$FINAL_PNA' — the org Modify policy reverted it (tag exclusion not honored?)"
  log "firewall updated ✓ (publicNetworkAccess=Enabled)"
fi

# ---------------------------------------------------------------------------
# 5. seed the canonical_map so L2 similarity + L3 alias rewrite work.
# ---------------------------------------------------------------------------
if [[ "$DO_SEED" -eq 1 ]]; then
  VENV="$REPO/tools-cli/.venv"
  if [[ ! -d "$VENV" ]]; then
    log "creating tools-cli venv (first run)"
    python3 -m venv "$VENV"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    pip install -q -r "$REPO/tools-cli/requirements.txt"
  else
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
  fi
  log "seeding canonical_map (idempotent upserts)"
  # Firewall changes can take a moment to reach the data plane; retry briefly.
  seeded=0
  for attempt in 1 2 3 4 5; do
    if python3 "$REPO/tools-cli/seed_canonical_map.py" >/tmp/seed-canonical-map.log 2>&1; then
      seeded=1; break
    fi
    warn "seed attempt $attempt failed (firewall may still be propagating); retrying in 10s"
    sleep 10
  done
  deactivate 2>/dev/null || true
  [[ "$seeded" -eq 1 ]] || die "seeding failed after retries (see /tmp/seed-canonical-map.log)"
  log "canonical_map seeded ✓ ($(grep -c '^\[ok\]' /tmp/seed-canonical-map.log 2>/dev/null || echo '?') docs)"
fi

log "cosmos ready ✓"
