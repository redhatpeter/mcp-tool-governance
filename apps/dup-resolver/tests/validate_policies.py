"""Validate the L3 APIM policy queries against the live canonical_map.

This script does NOT touch the index. It runs the exact Cosmos SQL queries
that the two L3 policies issue (with the same parameter binding) so we can
catch shape mismatches between the writer and the policies BEFORE deploying
the policy XML to APIM. Run after every change to either:

  - apps/dup-resolver/canonical_map.py  (the writer)
  - apim/policies/canonical-rewrite.policy.xml  (the tools/call rewrite)
  - apim/policies/tools-list-filter.policy.xml  (the tools/list filter)

Usage:
    cd apps/dup-resolver && source .venv/bin/activate
    export COSMOS_ENDPOINT=https://cosmoslab82658.documents.azure.com:443/
    python3 tests/validate_policies.py

Exit codes:
    0  — all assertions passed
    1  — at least one assertion failed (mismatch between writer & policy expectation)
    2  — Cosmos not reachable / canonical_map empty (run ingest first)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running as `python3 tests/validate_policies.py` from the
# dup-resolver/ folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import canonical_map
import config


# Cases probed against the demo data. After running ingest with the
# OpenAPI source, messy-mcp's createCustomer / Create_Customer cluster
# round-trips through customer_create as canonical, and invoice_create_v2
# rewrites to invoice_create_v1. We assert that exact behavior here.
TOOLS_CALL_CASES = [
    # (server, requested_wire_name, expected_canonical_wire_name, comment)
    ("messy-mcp", "createCustomer",   "customer_create",
     "createCustomer is an alias of customer_create"),
    ("messy-mcp", "Create_Customer",  "customer_create",
     "Create_Customer is an alias of customer_create"),
    ("messy-mcp", "customer_create",  "customer_create",
     "already canonical — no rewrite"),
    ("messy-mcp", "invoice_create_v2","invoice_create_v1",
     "v2 is an alias of v1 (per the election)"),
    ("messy-mcp", "invoice_create_v1","invoice_create_v1",
     "already canonical"),
    ("governed-mcp", "financeCustomerCreate", "financeCustomerCreate",
     "singleton cluster — passes through"),
    ("messy-mcp", "this_tool_does_not_exist", "this_tool_does_not_exist",
     "unknown tool — fail-open passes through"),
]


# Cases for the tools/list filter. Expected drop set is:
#   - every alias in any cluster whose canonical_server == this server
#     OR whose members include this server
TOOLS_LIST_CASES = {
    # server: set(expected fully-qualified ids in the drop set)
    "messy-mcp": {
        "messy-mcp__createCustomer",
        "messy-mcp__Create_Customer",
        "messy-mcp__invoice_create_v2",
    },
    "governed-mcp": set(),  # no governed-mcp tool is currently aliased
}


def _container():
    c = canonical_map._container()
    if c is None:
        print("[fail] canonical_map disabled — set COSMOS_ENDPOINT and re-run",
              file=sys.stderr)
        sys.exit(2)
    return c


def _query_tools_call_canonical(container, server: str,
                                requested_wire: str) -> str:
    """Replay the SQL the tools/call policy issues. Returns the canonical
    wire name to substitute, falling back to the requested name (fail-open)
    if no doc matches."""
    fqid = f"{server}__{requested_wire}"
    items = list(container.query_items(
        query=("SELECT VALUE c.primary.name FROM c "
               "WHERE c.id = @id OR ARRAY_CONTAINS(c.aliases, @id)"),
        parameters=[{"name": "@id", "value": fqid}],
        enable_cross_partition_query=True,
    ))
    if not items:
        return requested_wire   # fail-open
    return items[0]


def _query_tools_list_drop_set(container, server: str) -> set[str]:
    """Replay the SQL the tools/list filter issues. Returns the set of
    fully-qualified ids to drop from the outbound tools/list response."""
    items = list(container.query_items(
        query=("SELECT VALUE c.aliases FROM c "
               "WHERE c.canonical_server = @s "
               "OR EXISTS(SELECT VALUE m FROM m IN c.members WHERE m.server = @s)"),
        parameters=[{"name": "@s", "value": server}],
        enable_cross_partition_query=True,
    ))
    drop: set[str] = set()
    for arr in items:
        if isinstance(arr, list):
            drop.update(arr)
    return drop


def main() -> int:
    container = _container()
    # Sanity: any docs at all?
    count = list(container.query_items(
        query="SELECT VALUE COUNT(1) FROM c",
        enable_cross_partition_query=True,
    ))[0]
    if count == 0:
        print("[fail] canonical_map is empty — run ingest first", file=sys.stderr)
        return 2
    print(f"[info] canonical_map has {count} docs\n")

    failures: list[str] = []

    # --- tools/call rewrite ---
    print("=== tools/call rewrite (canonical-rewrite.policy.xml) ===")
    for server, requested, expected, note in TOOLS_CALL_CASES:
        actual = _query_tools_call_canonical(container, server, requested)
        ok = actual == expected
        marker = "✓" if ok else "✗"
        print(f"  {marker} {server} / {requested!r:30s} → {actual!r:30s} "
              f"(expected {expected!r}) — {note}")
        if not ok:
            failures.append(
                f"tools/call: {server}/{requested} → {actual} (want {expected})"
            )

    # --- tools/list filter ---
    print("\n=== tools/list filter (tools-list-filter.policy.xml) ===")
    for server, expected_drop in TOOLS_LIST_CASES.items():
        actual_drop = _query_tools_list_drop_set(container, server)
        missing = expected_drop - actual_drop
        unexpected = actual_drop - expected_drop
        ok = not missing and not unexpected
        marker = "✓" if ok else "✗"
        print(f"  {marker} {server}: drop set has {len(actual_drop)} ids "
              f"(expected {len(expected_drop)})")
        for d in sorted(actual_drop):
            print(f"      - {d}")
        if missing:
            failures.append(f"tools/list[{server}]: missing from drop set: {sorted(missing)}")
        if unexpected:
            failures.append(f"tools/list[{server}]: unexpected in drop set: {sorted(unexpected)}")

    # --- summary ---
    print()
    if failures:
        print(f"[FAIL] {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[OK] all assertions passed — writer and policy queries agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
