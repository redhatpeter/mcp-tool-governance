"""Orchestration: ingest from APIM, fingerprint, embed, cluster, elect, persist."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import config
import embed
import fingerprint as fp
import mcp_source
import search_client
from cluster import cluster as run_cluster
from elect import Candidate, elect


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_ingest() -> dict[str, Any]:
    """Pull → fingerprint → embed → upsert (no cluster yet) → cluster from index → elect → final upsert."""
    # 1. Pull current tools/list from every MCP server
    tools = mcp_source.fetch_all()
    if not tools:
        return {"status": "empty", "tools": 0}

    # Dedupe within a server: APIM-MCP can surface two operations with the
    # same wire name (a collision — failure mode #5). Keep the first; the
    # collision itself is reported by the L1 lint, not by L2.
    seen_ids: set[str] = set()
    deduped: list[fp.ToolDescriptor] = []
    collisions: list[str] = []
    for t in tools:
        if t.doc_id in seen_ids:
            collisions.append(t.doc_id)
            continue
        seen_ids.add(t.doc_id)
        deduped.append(t)
    tools = deduped

    # 2. Build fingerprint texts
    pairs = fp.fingerprint_many(tools)
    texts = [t for _, t in pairs]

    # 3. Embed in one call (PoC scale)
    vectors = embed.embed_texts(texts)

    # 4. Cluster in-memory by cosine sim
    vectors_by_id = {t.doc_id: v for (t, _), v in zip(pairs, vectors)}
    clusters_by_id = run_cluster(vectors_by_id, threshold=config.CLUSTER_THRESHOLD)

    # 5. Group + elect canonical per cluster
    by_cluster: dict[str, list[fp.ToolDescriptor]] = {}
    for (t, _), _v in zip(pairs, vectors):
        by_cluster.setdefault(clusters_by_id[t.doc_id], []).append(t)

    canonical_by_cluster: dict[str, dict[str, Any]] = {}
    for cid, members in by_cluster.items():
        cands = [Candidate(id=t.doc_id, server=t.server, name=t.name,
                           description=t.description) for t in members]
        winner, score, breakdown = elect(cands)
        canonical_by_cluster[cid] = {
            "winner_id": winner.id,
            "winner_name": winner.name,
            "score": score,
            "breakdown": breakdown,
            "members": [c.id for c in cands],
        }

    # 6. Build docs and upsert
    now = _now_iso()
    docs: list[dict[str, Any]] = []
    for (t, text), v in zip(pairs, vectors):
        cid = clusters_by_id[t.doc_id]
        winner = canonical_by_cluster[cid]
        domain, action, entity = fp.infer_domain_action_entity(t.name)
        docs.append({
            "id": t.doc_id,
            "server": t.server,
            "tool_name": t.name,
            "description": t.description,
            "fingerprint_text": text,
            "domain": domain or "",
            "action": action or "",
            "entity": entity or "",
            "cluster_id": cid,
            "canonical_id": winner["winner_id"],
            "is_canonical": (t.doc_id == winner["winner_id"]),
            "last_seen_utc": now,
            "embedding": v,
        })

    n = search_client.upsert_documents(docs)

    return {
        "status": "ok",
        "tools": len(tools),
        "clusters": len(by_cluster),
        "indexed": n,
        "collisions_dropped": collisions,
        "elections": canonical_by_cluster,
    }


if __name__ == "__main__":
    import json
    out = run_ingest()
    # Don't print full elections in CLI invocation
    summary = {k: v for k, v in out.items() if k != "elections"}
    summary["election_summary"] = {
        cid: {"winner": e["winner_name"], "score": round(e["score"], 3), "members": e["members"]}
        for cid, e in (out.get("elections") or {}).items()
    }
    print(json.dumps(summary, indent=2))
