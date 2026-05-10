"""Unit test: openapi_source uses APIM wire names when the map is provided.

Guards against regression of the canonical_map / runtime mismatch where
ingest emitted raw operationIds but APIM-MCP publishes camelCased wire
names. See apim_wirenames.py for the rationale.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openapi_source  # noqa: E402


SPEC = {
    "paths": {
        "/customers": {
            "post": {
                "operationId": "Create_Customer",
                "description": "Create one.",
            },
            "get": {
                "operationId": "customer_search",
                "description": "Search customers.",
            },
        },
        "/orphan": {
            "get": {
                "operationId": "not_in_apim_yet",
                "description": "Spec-only operation (not deployed).",
            },
        },
    }
}

WIRE_MAP = {
    "Create_Customer": "createCustomer",
    "customer_search": "customerSearch",
}


def test_extract_ops_uses_wire_names_when_present() -> None:
    tools = openapi_source._extract_ops(SPEC, "messy-mcp", WIRE_MAP)
    by_doc_id = {t.doc_id: t for t in tools}
    # Wire-named operations resolved correctly
    assert "messy-mcp__createCustomer" in by_doc_id
    assert "messy-mcp__customerSearch" in by_doc_id
    # Operations not in the APIM map fall back to operationId so ingest
    # still completes; downstream lint/check_pr can flag the drift.
    assert "messy-mcp__not_in_apim_yet" in by_doc_id
    # Sanity: the raw operationId is NOT silently used when a wire name
    # exists — that is the whole point.
    assert "messy-mcp__Create_Customer" not in by_doc_id
    assert "messy-mcp__customer_search" not in by_doc_id


def test_extract_ops_no_map_falls_back_to_op_id() -> None:
    tools = openapi_source._extract_ops(SPEC, "messy-mcp", {})
    by_doc_id = {t.doc_id: t for t in tools}
    # When APIM is unreachable, behaviour matches the pre-wire-name code.
    assert "messy-mcp__Create_Customer" in by_doc_id
    assert "messy-mcp__customer_search" in by_doc_id
    assert "messy-mcp__not_in_apim_yet" in by_doc_id


def test_short_op_extraction() -> None:
    """apim_wirenames._short_op handles both ARM paths and bare ids."""
    import apim_wirenames as wn
    full = ("/subscriptions/x/resourceGroups/y/providers/Microsoft.ApiManagement"
            "/service/z/apis/messy-mcp/operations/customer_create")
    assert wn._short_op(full) == "customer_create"
    assert wn._short_op("already_short") == "already_short"


if __name__ == "__main__":
    test_extract_ops_uses_wire_names_when_present()
    test_extract_ops_no_map_falls_back_to_op_id()
    test_short_op_extraction()
    print("OK: 3/3")
