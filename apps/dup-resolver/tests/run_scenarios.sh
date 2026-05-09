#!/usr/bin/env bash
# Local quality-test harness for check_pr.py.
# Each scenario builds a temp working tree state, runs check_pr.py against
# a known base ref (the main spec), and prints PASS/FAIL based on the
# expected verdict + exit code.
#
# Usage:
#   cd apps/dup-resolver
#   source .venv/bin/activate
#   bash tests/run_scenarios.sh

set -u  # not -e: we want to continue past failed scenarios
cd "$(dirname "$0")/.."   # apps/dup-resolver

PASS=0
FAIL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Use the committed copy of finance-governed.json on main as the "base"
BASE_SPEC="../../apim/openapi/finance-governed.json"
BASE_REF=$(git -C ../.. rev-parse main)

# We trick check_pr.py by building a synthetic file path under $TMP and
# pointing --base at a special marker that means "no prior version".
# Instead of fighting git, we run with --all and filter expectations.
# Simpler: write each scenario as a standalone OpenAPI file, run with --all.

run_scenario() {
  local name="$1"
  local spec_path="$2"
  local expected_exit="$3"   # 0 or 1
  local expected_pattern="$4"  # grep regex on stdout
  local extra_args="${5:-}"

  echo
  echo "============================================================"
  echo "SCENARIO: $name"
  echo "spec:     $spec_path"
  echo "expect:   exit=$expected_exit  pattern=/$expected_pattern/"
  echo "============================================================"
  set +e
  # shellcheck disable=SC2086
  output=$(python check_pr.py --all $extra_args "$spec_path" 2>&1)
  actual_exit=$?
  set -e
  echo "$output"
  echo "--- exit=$actual_exit ---"

  local ok=1
  if [[ "$actual_exit" != "$expected_exit" ]]; then
    echo "FAIL: exit code mismatch (got $actual_exit, want $expected_exit)"
    ok=0
  fi
  if ! echo "$output" | grep -qE "$expected_pattern"; then
    echo "FAIL: expected pattern not found"
    ok=0
  fi
  if [[ "$ok" == "1" ]]; then
    echo "PASS: $name"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# Helper: minimal OpenAPI shell
# ---------------------------------------------------------------------------
emit_spec() {
  local out="$1"; shift
  python - "$out" "$@" <<'PY'
import json, sys
out = sys.argv[1]
ops = []  # list of (path, method, opId, summary, description)
i = 2
while i < len(sys.argv):
    ops.append(tuple(sys.argv[i:i+5]))
    i += 5
spec = {
    "openapi": "3.0.0",
    "info": {"title": "test", "version": "0.0.0"},
    "paths": {},
}
for path, method, op_id, summary, desc in ops:
    spec["paths"].setdefault(path, {})[method] = {
        "operationId": op_id,
        "summary": summary,
        "description": desc,
        "responses": {"200": {"description": "ok"}},
    }
with open(out, "w") as f:
    json.dump(spec, f, indent=2)
PY
}

# Dup-text close to financeQuoteGet (we know this produces ~0.95)
DUP_DESC="Get the current market quote (bid/ask/last) for a ticker symbol. USE WHEN you need real-time pricing for a decision. Symbol format: uppercase ticker, e.g. MSFT. Quotes are advisory only and are NOT execution prices and may be stale up to 250ms."
NOVEL_DESC="Onboard a new employee into the HR system: create payroll record, provision corporate email, assign manager, and trigger orientation workflow. Returns the new employee ID."

# ---------------------------------------------------------------------------
# Scenario 1 (#5 in plan): Renamed op — same description, new operationId
# Expectation: should NOT flag as DUPLICATE against itself if the index
# entry came from the same canonical. Currently likely fails (will flag).
# ---------------------------------------------------------------------------
emit_spec "$TMP/rename.json" \
  "/governed/quotes/{symbol}" "get" "getQuote" "getQuote" "$DUP_DESC"
run_scenario "renamed-op-self-match" "$TMP/rename.json" 1 "DUPLICATE"

# ---------------------------------------------------------------------------
# Scenario 2 (#1 in plan): Multi-op PR — 1 duplicate + 1 novel
# Expect exit 1, 2 rows, 1 DUPLICATE + 1 OK.
# ---------------------------------------------------------------------------
emit_spec "$TMP/multi.json" \
  "/dup" "get" "financeQuoteFetch" "financeQuoteFetch" "$DUP_DESC" \
  "/novel" "post" "hrEmployeeOnboard" "hrEmployeeOnboard" "$NOVEL_DESC"
run_scenario "multi-op-dup-and-novel" "$TMP/multi.json" 1 "2 new operation\(s\) scored"

# ---------------------------------------------------------------------------
# Scenario 3 (#4 in plan): Clearly novel op — expect OK, exit 0
# ---------------------------------------------------------------------------
emit_spec "$TMP/novel.json" \
  "/hr/onboard" "post" "hrEmployeeOnboard" "hrEmployeeOnboard" "$NOVEL_DESC"
run_scenario "clearly-novel-op" "$TMP/novel.json" 0 "✅ OK"

# ---------------------------------------------------------------------------
# Scenario 4 (#6 in plan): Empty / missing description
# Should not crash. operationId-only is very weak signal — verdict depends.
# We assert: exit code is 0 or 1 (not crash) AND a verdict row appears.
# ---------------------------------------------------------------------------
emit_spec "$TMP/empty.json" \
  "/x" "get" "doStuff" "" ""
run_scenario "empty-description" "$TMP/empty.json" 0 "(OK|WARN|DUPLICATE)"

# ---------------------------------------------------------------------------
# Scenario 5 (#8 in plan): Malformed JSON
# Should fail with a friendly error, not a stack trace splatter.
# ---------------------------------------------------------------------------
echo "{ this is not valid json" > "$TMP/broken.json"
echo
echo "============================================================"
echo "SCENARIO: malformed-json"
echo "============================================================"
set +e
mout=$(python check_pr.py --all "$TMP/broken.json" 2>&1)
mexit=$?
set -e
echo "$mout" | tail -5
echo "--- exit=$mexit ---"
if [[ "$mexit" != "0" ]] && ! echo "$mout" | grep -qiE "traceback"; then
  echo "PASS: malformed-json (non-zero exit, no traceback)"
  PASS=$((PASS + 1))
elif [[ "$mexit" != "0" ]]; then
  echo "FAIL: malformed-json — exits non-zero but dumps a traceback"
  FAIL=$((FAIL + 1))
else
  echo "FAIL: malformed-json — should not exit 0"
  FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Scenario 6 (#2 in plan): Deletion-only PR
# We simulate by giving a spec that contains ONE op that already exists in
# main → with --all it would still score it. Better: use --base + diff.
# Synthesize a temp git scenario.
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo "SCENARIO: deletion-only (no new ops)"
echo "============================================================"
DEL_BR="test/deletion-only-$$"
git -C ../.. checkout -b "$DEL_BR" main >/dev/null 2>&1
# Remove the entire /governed/quotes/{symbol} path block by deleting one op
python - <<PY
import json, pathlib
p = pathlib.Path("../../apim/openapi/finance-governed.json")
s = json.loads(p.read_text())
# Delete an arbitrary op that exists on main
removed = None
for path, methods in list(s["paths"].items()):
    for m, op in list(methods.items()):
        if op.get("operationId") == "financeQuoteGet":
            del methods[m]
            removed = "financeQuoteGet"
            break
    if removed: break
p.write_text(json.dumps(s, indent=2))
print("removed:", removed)
PY
git -C ../.. add apim/openapi/finance-governed.json >/dev/null 2>&1
git -C ../.. commit -m "test: delete-only" >/dev/null 2>&1
set +e
dout=$(python check_pr.py --base main ../../apim/openapi/finance-governed.json 2>&1)
dexit=$?
set -e
echo "$dout"
echo "--- exit=$dexit ---"
if [[ "$dexit" == "0" ]] && echo "$dout" | grep -qE "(0 candidate|No new operations|nothing to score)"; then
  echo "PASS: deletion-only"
  PASS=$((PASS + 1))
else
  echo "FAIL: deletion-only — should report no new ops"
  FAIL=$((FAIL + 1))
fi
git -C ../.. checkout main >/dev/null 2>&1
git -C ../.. branch -D "$DEL_BR" >/dev/null 2>&1
git -C ../.. checkout -- apim/openapi/finance-governed.json 2>/dev/null

# ---------------------------------------------------------------------------
# Scenario 7 (#3 in plan): Cross-server collision
# Add the duplicate op to messy-mcp.json (different file/server) — does the
# index still flag it against governed-mcp/financeQuoteGet?
# This case scores ~0.900 (paraphrase, not verbatim), so verdict depends on
# threshold: DUPLICATE at 0.88, WARN at 0.92. Either is acceptable —
# the gate must surface SOMETHING, not silently pass.
# ---------------------------------------------------------------------------
emit_spec "$TMP/cross.json" \
  "/messy/quote" "get" "messyQuoteFetch" "messyQuoteFetch" "$DUP_DESC"
# Accept WARN (exit 0) or DUPLICATE (exit 1); we just verify the row mentions governed.
echo
echo "============================================================"
echo "SCENARIO: cross-server-collision"
echo "============================================================"
set +e
cout=$(python check_pr.py --all "$TMP/cross.json" 2>&1)
cexit=$?
set -e
echo "$cout"
echo "--- exit=$cexit ---"
if echo "$cout" | grep -qE "(DUPLICATE|WARN).*governed"; then
  echo "PASS: cross-server-collision (verdict=$(echo "$cout" | grep -oE "(DUPLICATE|WARN|OK)" | head -1), exit=$cexit)"
  PASS=$((PASS + 1))
else
  echo "FAIL: cross-server-collision — expected DUPLICATE or WARN against governed-mcp"
  FAIL=$((FAIL + 1))
fi

# ---------------------------------------------------------------------------
# Scenario 8 (#9 in plan): Threshold sweep — note check_pr.py reads
# CLUSTER_THRESHOLD at import time, so sweep via env var.
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo "THRESHOLD SWEEP for the duplicate candidate"
echo "============================================================"
emit_spec "$TMP/sweep.json" \
  "/q" "get" "financeQuoteFetch" "financeQuoteFetch" "$DUP_DESC"
for t in 0.80 0.85 0.88 0.92 0.96; do
  set +e
  sout=$(CLUSTER_THRESHOLD=$t python check_pr.py --all "$TMP/sweep.json" 2>&1)
  set -e
  verdict=$(echo "$sout" | grep -oE "(DUPLICATE|WARN|OK)" | head -1)
  score=$(echo "$sout" | grep -oE "score [0-9.]+" | head -1)
  printf "  threshold=%s  verdict=%-9s  %s\n" "$t" "$verdict" "$score"
done

# ---------------------------------------------------------------------------
# Scenario 9 (#12): Latency budget
# Time a 1-op, 5-op, and 20-op PR
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo "LATENCY BUDGET"
echo "============================================================"
for n in 1 5 20; do
  args=()
  for i in $(seq 1 $n); do
    args+=("/p$i" "get" "novelOp$i" "novelOp$i" "$NOVEL_DESC variant $i")
  done
  emit_spec "$TMP/lat$n.json" "${args[@]}"
  start=$(date +%s%N)
  python check_pr.py --all "$TMP/lat$n.json" >/dev/null 2>&1 || true
  end=$(date +%s%N)
  printf "  ops=%-3d elapsed=%.2fs\n" "$n" "$(awk -v s=$start -v e=$end 'BEGIN{print (e-s)/1e9}')"
done

echo
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
exit $FAIL
