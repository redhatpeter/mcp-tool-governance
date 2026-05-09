"""Provision the AI Search index. Idempotent.

Usage:
    python provision_index.py            # create if missing
    python provision_index.py --recreate # drop and recreate
"""
from __future__ import annotations

import argparse
import sys

import config
import search_client


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true",
                    help="drop the index first (data loss)")
    args = ap.parse_args()

    print(f"Endpoint: {config.SEARCH_ENDPOINT}")
    print(f"Index   : {config.SEARCH_INDEX}  (dims={config.EMBEDDING_DIMS})")

    if args.recreate:
        print("Dropping existing index...")
        search_client.drop_index()

    status = search_client.ensure_index()
    print(f"Index status: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
