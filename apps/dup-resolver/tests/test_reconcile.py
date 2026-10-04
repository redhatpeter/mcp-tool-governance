"""Regression test for canonical_map.reconcile().

Alias docs written by tools-cli/seed_canonical_map.py have their own ``id``
but share the canonical's ``canonical_id`` (the partition key). reconcile()
must decide staleness by ``canonical_id``; comparing ``id`` deleted every
alias on each ingest and broke the L3 alias rewrite.

Run from apps/dup-resolver/ (so config + canonical_map import cleanly).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import canonical_map  # noqa: E402


class _FakeContainer:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = list(docs)
        self.deleted: list[tuple[str, str]] = []

    def query_items(self, **_kwargs):
        return [{"id": d["id"], "canonical_id": d["canonical_id"]} for d in self.docs]

    def delete_item(self, item: str, partition_key: str) -> None:
        self.deleted.append((item, partition_key))


def _run(docs: list[dict], active: list[str]) -> _FakeContainer:
    fake = _FakeContainer(docs)
    original = canonical_map._container
    canonical_map._container = lambda: fake
    try:
        canonical_map.reconcile(active)
    finally:
        canonical_map._container = original
    return fake


def test_alias_docs_survive_when_canonical_is_active() -> None:
    docs = [
        {"id": "governed-mcp__financeQuoteGet", "canonical_id": "governed-mcp__financeQuoteGet"},
        {"id": "governed-mcp__get_quote", "canonical_id": "governed-mcp__financeQuoteGet"},
        {"id": "governed-mcp__fetch_quote", "canonical_id": "governed-mcp__financeQuoteGet"},
    ]
    fake = _run(docs, ["governed-mcp__financeQuoteGet"])
    assert fake.deleted == [], f"alias docs wrongly deleted: {fake.deleted}"


def test_docs_for_inactive_canonical_are_deleted() -> None:
    docs = [
        {"id": "governed-mcp__financeQuoteGet", "canonical_id": "governed-mcp__financeQuoteGet"},
        {"id": "messy-mcp__old_alias", "canonical_id": "messy-mcp__gone"},
        {"id": "messy-mcp__gone", "canonical_id": "messy-mcp__gone"},
    ]
    fake = _run(docs, ["governed-mcp__financeQuoteGet"])
    assert sorted(fake.deleted) == [
        ("messy-mcp__gone", "messy-mcp__gone"),
        ("messy-mcp__old_alias", "messy-mcp__gone"),
    ], fake.deleted


if __name__ == "__main__":
    test_alias_docs_survive_when_canonical_is_active()
    test_docs_for_inactive_canonical_are_deleted()
    print("ok: 2 reconcile tests")
