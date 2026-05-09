"""FastAPI thin wrapper around the resolver library.

Endpoints:
  GET  /healthz       — liveness + index doc count
  POST /ingest        — re-ingest from APIM (governed-mcp + messy-mcp)
  GET  /clusters      — dump current clusters from the index
  POST /similarity    — L1 CI hook: embed a candidate tool, return verdict
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

import config
import embed
import fingerprint as fp
import ingest as ingest_mod
import search_client


app = FastAPI(title="MCP Tool Governance — Dup-Resolver", version="0.1.0")


# ---------- /healthz ----------
@app.get("/healthz")
def healthz() -> dict[str, Any]:
    try:
        n = search_client.count_documents()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "index": config.SEARCH_INDEX, "doc_count": n,
            "threshold": config.CLUSTER_THRESHOLD, "dims": config.EMBEDDING_DIMS}


# ---------- /ingest ----------
@app.post("/ingest")
def ingest() -> dict[str, Any]:
    return ingest_mod.run_ingest()


# ---------- /clusters ----------
@app.get("/clusters")
def clusters() -> dict[str, Any]:
    docs = search_client.all_documents(select=[
        "id", "server", "tool_name", "cluster_id", "canonical_id",
        "is_canonical", "domain", "action",
    ])
    by_cluster: dict[str, dict[str, Any]] = {}
    for d in docs:
        cid = d.get("cluster_id") or "?"
        slot = by_cluster.setdefault(cid, {"cluster_id": cid, "canonical": None, "members": []})
        slot["members"].append({
            "id": d["id"], "server": d["server"], "name": d["tool_name"],
            "is_canonical": bool(d.get("is_canonical")),
        })
        if d.get("is_canonical"):
            slot["canonical"] = d["tool_name"]
    return {
        "total_tools": len(docs),
        "total_clusters": len(by_cluster),
        "duplicates": sum(1 for c in by_cluster.values() if len(c["members"]) > 1),
        "clusters": sorted(by_cluster.values(), key=lambda c: c["cluster_id"]),
    }


# ---------- /similarity ----------
class SimilarityRequest(BaseModel):
    """A candidate tool from a PR — same shape an OpenAPI op produces."""
    name: str = Field(..., description="proposed wire name")
    description: str = ""
    domain: str = ""
    server: str = "governed-mcp"  # candidate is presumed to be on the governed surface
    required_params: list[str] = []


class SimilarityHit(BaseModel):
    id: str
    server: str
    name: str
    score: float
    cluster_id: str | None = None
    canonical_id: str | None = None
    is_canonical: bool = False


class SimilarityResponse(BaseModel):
    verdict: str           # "DUPLICATE" | "WARN" | "OK"
    threshold: float
    cluster_id: str | None
    nearest: list[SimilarityHit]
    reason: str


@app.post("/similarity", response_model=SimilarityResponse)
def similarity(req: SimilarityRequest) -> SimilarityResponse:
    # Build a transient ToolDescriptor + fingerprint text just like ingest does
    desc = fp.ToolDescriptor(
        server=req.server, name=req.name, description=req.description,
        input_schema={"required": req.required_params} if req.required_params else {},
    )
    text = fp.fingerprint_text(desc)
    vec = embed.embed_one(text)

    hits_raw = search_client.vector_query(vec, k=5, select=[
        "id", "server", "tool_name", "cluster_id", "canonical_id", "is_canonical",
    ])
    hits = [
        SimilarityHit(
            id=h["id"], server=h["server"], name=h["tool_name"],
            score=float(h.get("_score") or 0.0),
            cluster_id=h.get("cluster_id"),
            canonical_id=h.get("canonical_id"),
            is_canonical=bool(h.get("is_canonical")),
        )
        for h in hits_raw
    ]

    if not hits:
        return SimilarityResponse(
            verdict="OK", threshold=config.CLUSTER_THRESHOLD,
            cluster_id=None, nearest=[],
            reason="index is empty — run /ingest first",
        )

    top = hits[0]
    # @search.score on cosine HNSW is rescaled; treat >= threshold as DUPLICATE,
    # within 0.05 below threshold as WARN.
    t = config.CLUSTER_THRESHOLD
    if top.score >= t:
        verdict = "DUPLICATE"
        reason = (f"top match '{top.name}' on {top.server} (score {top.score:.3f} ≥ {t}); "
                  f"would join cluster {top.cluster_id}; canonical={top.canonical_id}")
    elif top.score >= t - 0.05:
        verdict = "WARN"
        reason = (f"top match '{top.name}' (score {top.score:.3f}) is close to threshold "
                  f"{t}; reviewer should confirm not a duplicate")
    else:
        verdict = "OK"
        reason = f"no near-duplicates (top score {top.score:.3f} < {t})"

    return SimilarityResponse(
        verdict=verdict, threshold=t,
        cluster_id=(top.cluster_id if verdict == "DUPLICATE" else None),
        nearest=hits, reason=reason,
    )
