"""Cosmos writer for the L2 → L3 handoff (canonical_map).

L2 (this app) elects a canonical tool per cluster. L3 (future APIM policy)
needs to read that decision at runtime. This module bridges the two via a
Cosmos SQL container — one document per cluster, partitioned by
``canonical_id``, point-readable by L3.

Schema (one doc per cluster):

    {
      "id":              "<canonical_id>",   # == the canonical's tool doc_id
      "canonical_id":    "<canonical_id>",   # == partition key
      "cluster_id":      "<cluster_id from L2>",
      "canonical_server":"<server>",
      "canonical_name":  "<wire name>",
      "score":           0.85,
      "score_breakdown": {...},
      "members": [
        {"id": "<doc_id>", "server": "...", "name": "...", "is_canonical": bool},
        ...
      ],
      "members_count":   3,
      "last_updated_utc":"2026-05-10T...",
      "ingest_run_id":   "<GITHUB_SHA or uuid>"
    }

Auth precedence (mirrors search_client):
    1. ``COSMOS_KEY`` env var (preferred for CI)
    2. ``COSMOS_KEY_FILE`` pointing to a file with the master key
    3. ``DefaultAzureCredential`` (RBAC, when the account allows AAD)

If ``COSMOS_ENDPOINT`` is empty the writer **no-ops** and logs once.
This keeps the rest of ingest working in environments where Cosmos
isn't wired up yet (local dev, early CI).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable

import config

# Optional import — without azure-cosmos we silently no-op too.
try:
    from azure.cosmos import CosmosClient, PartitionKey, exceptions as cosmos_exceptions
    _COSMOS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _COSMOS_AVAILABLE = False
    cosmos_exceptions = None  # type: ignore


_DISABLED_LOGGED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return os.environ.get("GITHUB_SHA") or str(uuid.uuid4())


def _disabled_reason() -> str | None:
    if not _COSMOS_AVAILABLE:
        return "azure-cosmos not installed"
    if not config.COSMOS_ENDPOINT:
        return "COSMOS_ENDPOINT not set"
    return None


def _log_disabled_once(reason: str) -> None:
    global _DISABLED_LOGGED
    if _DISABLED_LOGGED:
        return
    print(
        f"[canonical_map] disabled: {reason} — skipping Cosmos write",
        file=sys.stderr,
    )
    _DISABLED_LOGGED = True


@lru_cache(maxsize=1)
def _container():
    """Return the Cosmos container client, or None if disabled.

    Cached so the auth handshake happens once per process.
    """
    reason = _disabled_reason()
    if reason:
        _log_disabled_once(reason)
        return None

    key = config.cosmos_key()
    if key:
        client = CosmosClient(config.COSMOS_ENDPOINT, credential=key)
    else:
        # AAD fallback — requires `Cosmos DB Built-in Data Contributor` (or
        # tighter) on the principal. Won't work on accounts that have
        # disabled AAD data-plane.
        client = CosmosClient(config.COSMOS_ENDPOINT, credential=config.credential())

    db = client.get_database_client(config.COSMOS_DATABASE)
    return db.get_container_client(config.COSMOS_CONTAINER)


def _to_doc(cid: str, election: dict, run_id: str) -> dict[str, Any]:
    """Build the Cosmos document for a single cluster's election outcome."""
    canonical_id = election["winner_id"]
    members_meta: list[dict[str, Any]] = []
    for member_id in election["members"]:
        # member_id is "<server>__<wire_name>". Split on the first "__" so
        # wire names containing underscores stay intact.
        if "__" in member_id:
            server, _, name = member_id.partition("__")
        else:
            server, name = "", member_id
        members_meta.append({
            "id": member_id,
            "server": server,
            "name": name,
            "is_canonical": member_id == canonical_id,
        })

    canonical_meta = next(
        (m for m in members_meta if m["is_canonical"]),
        {"server": "", "name": election.get("winner_name", "")},
    )

    return {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "cluster_id": cid,
        "canonical_server": canonical_meta["server"],
        "canonical_name": canonical_meta["name"] or election.get("winner_name", ""),
        "score": float(election.get("score", 0.0)),
        "score_breakdown": dict(election.get("breakdown") or {}),
        "members": members_meta,
        "members_count": len(members_meta),
        "last_updated_utc": _now_iso(),
        "ingest_run_id": run_id,
    }


def upsert_clusters(canonical_by_cluster: dict[str, dict],
                    run_id: str | None = None) -> dict[str, Any]:
    """Upsert one doc per cluster. No-op if Cosmos isn't configured.

    Returns a small status dict (always — never raises just because Cosmos
    is unconfigured; that's the whole point of the optional-by-default
    design).
    """
    container = _container()
    if container is None:
        return {"written": 0, "skipped": len(canonical_by_cluster),
                "active_canonical_ids": [], "disabled": True}

    rid = run_id or _run_id()
    written = 0
    failures: list[str] = []
    active_ids: list[str] = []
    for cid, election in canonical_by_cluster.items():
        doc = _to_doc(cid, election, rid)
        active_ids.append(doc["canonical_id"])
        try:
            container.upsert_item(doc)
            written += 1
        except cosmos_exceptions.CosmosHttpResponseError as e:  # type: ignore[union-attr]
            failures.append(f"{doc['canonical_id']}: {e.message}")
    return {
        "written": written,
        "skipped": 0,
        "failures": failures,
        "active_canonical_ids": active_ids,
        "disabled": False,
    }


def reconcile(active_canonical_ids: Iterable[str]) -> dict[str, Any]:
    """Delete canonical_map docs whose canonical_id is no longer active.

    Mirrors the AI Search ghost-doc cleanup in ``ingest.py``: anything in
    Cosmos that L2 didn't just write is stale (cluster dissolved, canonical
    re-elected to a different tool, server removed).
    """
    container = _container()
    if container is None:
        return {"deleted": 0, "stale_ids": [], "disabled": True}

    active = set(active_canonical_ids)
    # Single-partition cross-partition query is fine at PoC scale.
    existing = list(container.query_items(
        query="SELECT c.id, c.canonical_id FROM c",
        enable_cross_partition_query=True,
    ))
    stale = [d for d in existing if d["id"] not in active]
    deleted = 0
    failures: list[str] = []
    for d in stale:
        try:
            container.delete_item(item=d["id"], partition_key=d["canonical_id"])
            deleted += 1
        except cosmos_exceptions.CosmosHttpResponseError as e:  # type: ignore[union-attr]
            failures.append(f"{d['id']}: {e.message}")
    return {
        "deleted": deleted,
        "stale_ids": [d["id"] for d in stale],
        "failures": failures,
        "disabled": False,
    }


def read_canonical(canonical_id: str) -> dict | None:
    """Point-read helper. Useful for L3 / debugging. Returns None if absent
    or if Cosmos is disabled."""
    container = _container()
    if container is None:
        return None
    try:
        return container.read_item(item=canonical_id, partition_key=canonical_id)
    except cosmos_exceptions.CosmosResourceNotFoundError:  # type: ignore[union-attr]
        return None
