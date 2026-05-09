"""Deterministic weighted-score canonical election.

For each cluster, score every member tool and pick the highest. Ties broken
by smallest tool_id (deterministic). The score is replayable from the same
inputs — no LLM judge involved (per ARCHITECTURE.md §14).

Score (0..1, higher = better canonical):

  + W_GOVERNED   if server == 'governed-mcp'
  + W_NAME       if name passes the L1 wire-name regex (lint E002 shape)
  + W_DOMAIN     if name starts with an approved domain prefix (lint E004)
  + W_VERB       if last name token is in approved verb list (lint E005)
  + W_DESC       if description >= 80 chars
  + W_GUIDANCE   if description contains 'USE WHEN' or 'DO NOT USE'

Weights sum to 1.0; missing penalty = 0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


W_GOVERNED = 0.30
W_NAME     = 0.10
W_DOMAIN   = 0.15
W_VERB     = 0.10
W_DESC     = 0.15
W_GUIDANCE = 0.20

WIRE_NAME_RE = re.compile(r"^[a-z][a-zA-Z0-9]{2,63}$")
DOMAINS = ("finance", "customer", "hr", "sales", "operations")
VERBS = {
    "get", "list", "search", "create", "update", "delete", "summarize",
    "validate", "approve", "reject", "void",
}
_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _last_token(name: str) -> str:
    raw = [t for t in _SPLIT.split(name) if t]
    parts: list[str] = []
    for piece in raw:
        parts.extend(t for t in _CAMEL.split(piece) if t)
    return parts[-1].lower() if parts else ""


@dataclass
class Candidate:
    id: str           # "<server>/<wire_name>"
    server: str       # "governed-mcp" / "messy-mcp"
    name: str         # wire name
    description: str


def score(c: Candidate) -> tuple[float, dict]:
    """Return (final_score, breakdown) for transparency / debugging."""
    b: dict[str, float] = {}
    b["governed"] = W_GOVERNED if c.server == "governed-mcp" else 0.0
    b["name"]     = W_NAME if WIRE_NAME_RE.match(c.name or "") else 0.0
    b["domain"]   = W_DOMAIN if any((c.name or "").startswith(d) for d in DOMAINS) else 0.0
    last = _last_token(c.name or "")
    b["verb"]     = W_VERB if last in VERBS else 0.0
    b["desc"]     = W_DESC if len(c.description or "") >= 80 else 0.0
    desc_low = (c.description or "").lower()
    b["guidance"] = W_GUIDANCE if ("use when" in desc_low or "do not use" in desc_low) else 0.0
    total = sum(b.values())
    return total, b


def elect(candidates: list[Candidate]) -> tuple[Candidate, float, dict]:
    """Returns (winner, score, breakdown). Tie-break: smallest id."""
    if not candidates:
        raise ValueError("no candidates")
    scored = [(score(c), c) for c in candidates]
    # Sort: highest score first, then smallest id
    scored.sort(key=lambda t: (-t[0][0], t[1].id))
    (best_score, best_breakdown), winner = scored[0]
    return winner, best_score, best_breakdown
