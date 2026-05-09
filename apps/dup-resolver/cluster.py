"""Single-linkage clustering at cosine threshold 0.88.

Inputs: { id: vector } dict.
Output: { id: cluster_id } dict, with deterministic cluster ids assigned by
ordering on the smallest member id in each cluster.

We deliberately use single-linkage over k-means / DBSCAN because:
  - It needs no `k`.
  - It chains transitively, so 'A near B' and 'B near C' puts {A,B,C} together.
    Defensible: if any pair in a cluster is similar enough to merge, merge.
  - Easy to reason about + replay from the same vectors + threshold.

Implementation = union-find over edges where cosine(a,b) >= threshold.
"""
from __future__ import annotations

from typing import Iterable
import math


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Make the smaller id the root, so cluster ids are stable + named-by-min
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def cluster(vectors_by_id: dict[str, list[float]], *, threshold: float = 0.88) -> dict[str, str]:
    """Returns { tool_id -> cluster_id } where cluster_id is 'clu_<min_member>'."""
    ids = sorted(vectors_by_id.keys())
    uf = _UnionFind(ids)

    # All-pairs is fine for PoC scale (≤ 100).
    for i, a in enumerate(ids):
        va = vectors_by_id[a]
        for b in ids[i + 1 :]:
            vb = vectors_by_id[b]
            if _cosine(va, vb) >= threshold:
                uf.union(a, b)

    # Materialize cluster_id from the root member id (already smallest by union rule)
    return {i: f"clu_{uf.find(i)}" for i in ids}
