"""Build the canonical fingerprint text that goes into the embedding.

The fingerprint is a single newline-joined string with stable structure so
that two semantically similar tools produce embeddings that cluster together
even when their names differ. We deliberately exclude wire names from the
text — clustering by *name* would defeat the purpose.

Schema (in order, each line):
  domain: <domain>
  action: <verb>
  entity: <noun>
  description: <description>
  params: <comma-separated required param names>

Tokens missing from the source are simply omitted (stable, not "(none)").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Same camelCase tokenizer as the lint
_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_VERBS = {
    "get", "list", "search", "create", "update", "delete", "summarize",
    "validate", "approve", "reject", "void", "fetch", "find", "lookup",
}


def _tokenize(s: str) -> list[str]:
    raw = [t for t in _SPLIT.split(s) if t]
    out: list[str] = []
    for piece in raw:
        out.extend(t.lower() for t in _CAMEL.split(piece) if t)
    return out


@dataclass
class ToolDescriptor:
    """A tool as it appears in an MCP tools/list response."""
    server: str          # e.g. "governed-mcp"
    name: str            # wire name, e.g. "financeQuoteGet"
    description: str     # full description string from inputSchema/op
    input_schema: dict   # JSON-Schema dict (may be None)

    @property
    def doc_id(self) -> str:
        # Index document key: server-scoped to allow same wire name across servers.
        # Azure AI Search keys allow only [A-Za-z0-9_=-]; '/' is rejected so we
        # use '__' as the server↔name separator.
        return f"{self.server}__{self.name}"

    def required_params(self) -> list[str]:
        if not isinstance(self.input_schema, dict):
            return []
        req = self.input_schema.get("required") or []
        return [str(r) for r in req if isinstance(r, str)]


def infer_domain_action_entity(name: str) -> tuple[str, str, str]:
    """Best-effort inference. Pure-token-heuristic, not authoritative."""
    toks = _tokenize(name)
    if not toks:
        return "", "", ""
    domain = toks[0] if toks else ""
    action = ""
    entity_parts: list[str] = []
    # Verb is whichever token is in _VERBS; entity = the rest excluding domain
    for t in toks[1:]:
        if not action and t in _VERBS:
            action = t
        else:
            entity_parts.append(t)
    if not action:  # fallback: last token as action
        action = toks[-1]
        entity_parts = toks[1:-1]
    return domain, action, " ".join(entity_parts)


def fingerprint_text(d: ToolDescriptor) -> str:
    domain, action, entity = infer_domain_action_entity(d.name)
    params = d.required_params()
    parts = []
    if domain:
        parts.append(f"domain: {domain}")
    if action:
        parts.append(f"action: {action}")
    if entity:
        parts.append(f"entity: {entity}")
    if d.description:
        parts.append(f"description: {d.description.strip()}")
    if params:
        parts.append("params: " + ", ".join(sorted(params)))
    return "\n".join(parts)


def fingerprint_many(descriptors: Iterable[ToolDescriptor]) -> list[tuple[ToolDescriptor, str]]:
    return [(d, fingerprint_text(d)) for d in descriptors]
