"""Read tool descriptors from OpenAPI specs in the repo.

This is an alternative to ``mcp_source`` (which calls the live APIM-MCP
gateway). Useful for CI workflows that run without APIM credentials —
especially the ``ingest-on-merge`` workflow, where the source of truth is
the spec files committed to ``main``.

Convention: each file under ``apim/openapi/<stem>.json`` defines the
operations exposed by an MCP server. The mapping from filename stem to
APIM MCP server name lives in ``apim/openapi/_servers.yaml`` (the
**spec-source manifest**) — adding a new server is a one-line edit, no
code change required.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from fingerprint import ToolDescriptor


# Built-in fallback used when the manifest is missing or unreadable. Keeps
# the CLI useful in unit tests / fresh checkouts. Real deployments should
# author apim/openapi/_servers.yaml.
_BUILTIN_FALLBACK = {
    "finance-governed": "governed-mcp",
    "finance-messy": "messy-mcp",
}

_MANIFEST_FILE = "_servers.yaml"


def _load_server_map(spec_dir: str | Path) -> dict[str, str]:
    """Return {filename_stem: server_name} from the manifest, or fall back."""
    manifest = Path(spec_dir) / _MANIFEST_FILE
    if not manifest.exists():
        return dict(_BUILTIN_FALLBACK)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        # PyYAML missing — degrade gracefully rather than crash CI.
        return dict(_BUILTIN_FALLBACK)
    try:
        data = yaml.safe_load(manifest.read_text()) or {}
    except yaml.YAMLError as e:
        raise RuntimeError(f"{manifest}: invalid YAML — {e}") from e
    servers = data.get("servers")
    if not isinstance(servers, dict) or not servers:
        raise RuntimeError(
            f"{manifest}: expected non-empty 'servers' mapping (stem → server name)"
        )
    # Normalize values to str; reject empty mappings to surface bad edits early.
    out: dict[str, str] = {}
    for stem, server in servers.items():
        if not isinstance(server, str) or not server:
            raise RuntimeError(
                f"{manifest}: server name for '{stem}' must be a non-empty string"
            )
        out[str(stem)] = server
    return out


# Resolve the manifest at import time against the configured spec dir, so
# downstream callers can keep treating ``SERVER_BY_FILE`` as a plain dict.
# The env var is read here directly (not via config) to keep this module
# importable from tests that don't set up the full config surface.
_DEFAULT_SPEC_DIR = os.environ.get("OPENAPI_SPEC_DIR", "apim/openapi")
SERVER_BY_FILE: dict[str, str] = _load_server_map(_DEFAULT_SPEC_DIR)


def reload_server_map(spec_dir: str | Path | None = None) -> dict[str, str]:
    """Re-read the manifest. Useful for tests that swap the spec dir."""
    global SERVER_BY_FILE
    SERVER_BY_FILE = _load_server_map(spec_dir or _DEFAULT_SPEC_DIR)
    return SERVER_BY_FILE


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
    server_map = _load_server_map(base)
    out: list[ToolDescriptor] = []
    for p in sorted(base.glob("*.json")):
        server = server_map.get(p.stem)
        if not server:
            # Unknown spec file — skip rather than guess. The manifest is
            # the gate; if a stem isn't listed there, the operator hasn't
            # opted in to ingesting it yet.
            continue
        try:
            spec = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{p}: not valid JSON ({e.msg} line {e.lineno})") from e
        out.extend(_extract_ops(spec, server))
    return out

