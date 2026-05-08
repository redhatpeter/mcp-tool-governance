"""Seed canonical_map documents into Cosmos for the MCP Tool Governance PoC.

Target: cosmoslab82658 / governance / mcp-canonical-map (PK /canonical_id).
Auth:   DefaultAzureCredential (uses your `az login`).

Document shape matches what apim/policies/canonical-rewrite.policy.xml expects.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential

ACCOUNT_URL = os.environ.get(
    "COSMOS_ACCOUNT_URL", "https://cosmoslab82658.documents.azure.com:443/"
)
DATABASE = os.environ.get("COSMOS_DATABASE", "governance")
CONTAINER = os.environ.get("COSMOS_CONTAINER", "mcp-canonical-map")

NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

# --------------------------------------------------------------------------- #
# Canonical map for the GET-only smoke demo on apimopenai99 / governed-mcp.
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
    docs: list[dict] = []
    for canonical, meta in CANONICALS.items():
        primary = {
            "name": canonical,
            "domain": meta["domain"],
            "entity": meta["entity"],
            "action": meta["action"],
        }
        # Self-doc: direct call to the canonical name.
        docs.append({
            "id": canonical,
            "canonical_id": canonical,
            "primary": primary,
            "aliases": meta["aliases"],
            "election": {"method": "seed", "at": NOW},
        })
        # One doc per alias — id == alias so the policy's
        # GET /docs/{requestedTool} resolves it.
        for alias in meta["aliases"]:
            docs.append({
                "id": alias,
                "canonical_id": alias,
                "primary": primary,
                "aliases": [],
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
