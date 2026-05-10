"""Read tool descriptors from OpenAPI specs in the repo.

This is an alternative to ``mcp_source`` (which calls the live APIM-MCP
gateway). Useful for CI workflows that run without APIM credentials —
especially the ``ingest-on-merge`` workflow, where the source of truth is
the spec files committed to ``main``.

Convention: each file under ``apim/openapi/<server>.json`` defines the
operations exposed by MCP server ``<server>``. The filename stem is the
server name (e.g. ``finance-governed.json`` → server ``governed-mcp``;
see SERVER_BY_FILE for the mapping).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from fingerprint import ToolDescriptor


# Map OpenAPI filename stem → MCP server name. Keep in sync with
# config.MCP_SERVERS and the APIM product configuration.
SERVER_BY_FILE = {
    "finance-governed": "governed-mcp",
    "finance-messy": "messy-mcp",
}


def _extract_ops(spec: dict, server: str) -> list[ToolDescriptor]:
    out: list[ToolDescriptor] = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId")
            if not op_id:
                continue
            out.append(ToolDescriptor(
                server=server,
                name=str(op_id),
                description=str(op.get("description") or op.get("summary") or ""),
                input_schema={},  # not used by fingerprint text today
            ))
    return out


def fetch_all(spec_dir: str | Path = "apim/openapi") -> list[ToolDescriptor]:
    """Read every *.json under ``spec_dir`` and emit ToolDescriptors."""
    base = Path(spec_dir)
    out: list[ToolDescriptor] = []
    for p in sorted(base.glob("*.json")):
        server = SERVER_BY_FILE.get(p.stem)
        if not server:
            # Unknown spec file — skip rather than guess
            continue
        try:
            spec = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{p}: not valid JSON ({e.msg} line {e.lineno})") from e
        out.extend(_extract_ops(spec, server))
    return out
