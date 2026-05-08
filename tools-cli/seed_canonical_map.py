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

SEEDS: list[dict] = [
    {
        "id": "get_customer",
        "canonical_id": "get_customer",
        "primary": {
            "name": "crm_customer_get",
            "domain": "crm",
            "entity": "customer",
            "action": "get",
        },
        "aliases": ["get_customer", "fetch_customer"],
        "election": {"method": "seed", "at": NOW},
    },
    {
        "id": "crm_customer_get",
        "canonical_id": "crm_customer_get",
        "primary": {
            "name": "crm_customer_get",
            "domain": "crm",
            "entity": "customer",
            "action": "get",
        },
        "aliases": [],
        "election": {"method": "seed", "at": NOW},
    },
]


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
