"""Seed canonical_map documents into Cosmos for the MCP Tool Governance PoC.

Target: cosmoslab826582 / governance / mcp-canonical-map (PK /canonical_id).
Auth:   DefaultAzureCredential (uses your `az login`).

Document shape matches what apim/policies/canonical-rewrite.policy.xml expects.

FQID convention
---------------
The L3 inbound canonical-rewrite policy looks up the requested tool by
``"<server>__<wire_name>"`` ("FQID"). Cosmos doc ids therefore MUST be
FQID-prefixed too, otherwise the policy's `c.id = @id` clause never
matches and aliases fall through unrewritten.

This seed only writes **alias docs** (ids of the form
``governed-mcp__<alias>``); the canonical self-doc is owned by
``apps/dup-resolver/canonical_map.py`` (L2 → L3 handoff). Each alias
doc carries the canonical's FQID as ``canonical_id`` (the partition
key), so all aliases for one canonical live in the same partition and
survive the dup-resolver reconcile() sweep (which keeps any doc whose
``canonical_id`` is in the active set).
"""

from __future__ import annotations

import datetime as dt
import os
import sys

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential

ACCOUNT_URL = os.environ.get(
    "COSMOS_ACCOUNT_URL", "https://cosmoslab826582.documents.azure.com:443/"
)
DATABASE = os.environ.get("COSMOS_DATABASE", "governance")
CONTAINER = os.environ.get("COSMOS_CONTAINER", "mcp-canonical-map")

# MCP server name; used to build FQIDs that match the live L3 policy.
SERVER = os.environ.get("MCP_SERVER_NAME", "governed-mcp")

NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _fqid(name: str) -> str:
    """Build the fully-qualified id used as the Cosmos doc id."""
    return f"{SERVER}__{name}"

# --------------------------------------------------------------------------- #
# Canonical map for the GET-only smoke demo on apimopenai992 / governed-mcp.
#
# Wire names (what APIM-MCP actually exposes after camelCasing the OpenAPI
# operation summaries) for the 5 GET ops in finance-governed.json:
#   financeCustomerGet, financeCustomerSearch, financeInvoiceGet,
#   financeInvoiceList, financeQuoteGet
#
# Each canonical gets a self-doc (so direct calls also pass the lookup), plus
# one doc per alias name an LLM might plausibly emit. The policy reads
# `primary.name` from whichever doc matches `params.name` and rewrites the
# JSON-RPC body if alias != canonical.
#
# POST ops (financeCustomerCreate / financeInvoiceCreate / financePaymentApprove)
# are intentionally excluded — they trip the APIM-MCP last-write-wins body bug
# (Azure-Samples/AI-Gateway #315).
# --------------------------------------------------------------------------- #

CANONICALS: dict[str, dict] = {
    "financeCustomerGet": {
        "domain": "finance",
        "entity": "customer",
        "action": "get",
        "aliases": [
            "get_customer",
            "get_finance_customer",
            "customer_get",
            "finance_customer_get",
            "fetch_customer",
        ],
    },
    "financeCustomerSearch": {
        "domain": "finance",
        "entity": "customer",
        "action": "search",
        "aliases": [
            "search_customers",
            "find_customer",
            "finance_customer_search",
            "customer_search",
        ],
    },
    "financeInvoiceGet": {
        "domain": "finance",
        "entity": "invoice",
        "action": "get",
        "aliases": [
            "get_invoice",
            "get_finance_invoice",
            "invoice_get",
            "finance_invoice_get",
        ],
    },
    "financeInvoiceList": {
        "domain": "finance",
        "entity": "invoice",
        "action": "list",
        "aliases": [
            "list_invoices",
            "list_finance_invoices",
            "finance_invoice_list",
            "invoices_list",
        ],
    },
    "financeQuoteGet": {
        "domain": "finance",
        "entity": "quote",
        "action": "get",
        "aliases": [
            "get_quote",
            "get_finance_quote",
            "quote_get",
            "finance_quote_get",
            "fetch_quote",
        ],
    },
}


def _build_seeds() -> list[dict]:
    """One alias doc per (canonical, alias) pair; FQID-prefixed.

    The canonical self-doc is intentionally NOT seeded — the dup-resolver
    writes it with the authoritative election metadata. Seeding it here
    would clobber that on every run.
    """
    docs: list[dict] = []
    for canonical, meta in CANONICALS.items():
        canonical_fqid = _fqid(canonical)
        primary = {
            "id": canonical_fqid,
            "server": SERVER,
            "name": canonical,
            "domain": meta["domain"],
            "entity": meta["entity"],
            "action": meta["action"],
        }
        for alias in meta["aliases"]:
            docs.append({
                "id": _fqid(alias),
                "canonical_id": canonical_fqid,   # partition key
                "canonical_server": SERVER,
                "primary": primary,
                "aliases": [],
                "is_alias_seed": True,
                "election": {"method": "seed", "at": NOW},
            })
    return docs


SEEDS: list[dict] = _build_seeds()


def main() -> int:
    cred = DefaultAzureCredential()
    client = CosmosClient(ACCOUNT_URL, credential=cred)
    db = client.get_database_client(DATABASE)
    container = db.get_container_client(CONTAINER)

    for doc in SEEDS:
        try:
            container.upsert_item(doc)
            print(
                f"[ok] upserted id={doc['id']:<24} -> primary.name={doc['primary']['name']}"
            )
        except exceptions.CosmosHttpResponseError as e:
            print(f"[err] id={doc['id']}: {e.message}", file=sys.stderr)
            return 1

    print(f"\nSeeded {len(SEEDS)} doc(s) into {DATABASE}/{CONTAINER}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
