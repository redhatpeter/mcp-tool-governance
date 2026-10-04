"""Resolve operationId → MCP wire name from APIM as the source of truth.

Why this exists
---------------
APIM-MCP exposes each backing operation under a *wire name* that it
derives from the operation's `operationId` (typically a camelCase
normalization). The transformation is owned by APIM and may evolve;
the only authoritative answer is what APIM itself publishes on the
MCP-typed API resource at
``properties.mcpTools[*].{name, operationId}``.

The runtime ``tools/list`` response uses these wire names. If our
ingest stores raw OpenAPI operationIds instead, the canonical_map
keys (`<server>__<id>`) won't match what the L3 outbound filter sees,
and aliases silently fail to drop.

This module performs one ARM GET per MCP server, returning a
``{operationId: wire_name}`` map. The lookup is cached for the
process lifetime — ingest is short-lived and one call per server is
cheap. Failure modes are explicit and non-fatal: a missing/empty map
causes the caller to fall back to the raw operationId (with a
warning), so ingest still completes when APIM is unreachable.

Inputs (env)
------------
APIM_SUBSCRIPTION_ID   Azure subscription containing APIM.
APIM_RESOURCE_GROUP    Resource group of the APIM instance.
APIM_SERVICE_NAME      APIM service name. Defaults to the host
                       portion of APIM_GATEWAY_BASE
                       (``apimopenai992.azure-api.net`` -> ``apimopenai992``).

Auth: DefaultAzureCredential (same OIDC path as the rest of ingest).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Mapping
from urllib.parse import urlparse

import httpx

import config

_log = logging.getLogger(__name__)

_API_VERSION = "2025-03-01-preview"
_ARM_SCOPE = "https://management.azure.com/.default"


def _service_name() -> str:
    """Derive APIM service name. Explicit env wins; else parse the gateway host."""
    explicit = os.environ.get("APIM_SERVICE_NAME", "").strip()
    if explicit:
        return explicit
    host = urlparse(config.APIM_GATEWAY_BASE).hostname or ""
    # Conventional gateway host: <service>.azure-api.net
    return host.split(".", 1)[0] if host else ""


def _arm_token() -> str:
    return config.credential().get_token(_ARM_SCOPE).token


def _short_op(op_id_path: str) -> str:
    """Reduce ARM operation resource id to its trailing operation name.

    APIM returns ``operationId`` as a full resource path:
    ``/subscriptions/.../apis/<api>/operations/<short>``. The OpenAPI spec's
    ``operationId`` corresponds to ``<short>``.
    """
    if "/operations/" in op_id_path:
        return op_id_path.rsplit("/operations/", 1)[1]
    return op_id_path


@lru_cache(maxsize=64)
def wire_name_map(server: str) -> Mapping[str, str]:
    """Return ``{operationId: wire_name}`` for the given MCP-typed APIM API.

    Returns an empty mapping (and logs a warning) if any of:
      * required env vars are missing,
      * the API doesn't exist or isn't an MCP-typed API,
      * the ARM call fails.

    Callers should treat an empty result as "fall back to operationId".
    """
    sub = os.environ.get("APIM_SUBSCRIPTION_ID", "").strip()
    rg = os.environ.get("APIM_RESOURCE_GROUP", "").strip()
    svc = _service_name()
    if not (sub and rg and svc):
        _log.warning(
            "wire_name_map(%s): APIM coordinates not fully set "
            "(APIM_SUBSCRIPTION_ID/APIM_RESOURCE_GROUP/APIM_SERVICE_NAME); "
            "wire-name resolution disabled, falling back to raw operationIds",
            server,
        )
        return {}

    url = (
        f"https://management.azure.com/subscriptions/{sub}"
        f"/resourceGroups/{rg}/providers/Microsoft.ApiManagement/service/{svc}"
        f"/apis/{server}?api-version={_API_VERSION}"
    )
    try:
        token = _arm_token()
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 404:
            _log.warning("wire_name_map(%s): API not found at %s", server, url)
            return {}
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        _log.warning("wire_name_map(%s): ARM lookup failed: %s", server, e)
        return {}

    tools = ((body.get("properties") or {}).get("mcpTools")) or []
    out: dict[str, str] = {}
    for t in tools:
        wire = t.get("name")
        op = t.get("operationId")
        if not (wire and op):
            continue
        short = _short_op(str(op))
        # Multiple operationIds can collapse to the same wire name (APIM
        # de-dupes on wire name in tools/list). That's a real collision the
        # L1 lint already flags; we still record both mappings so each
        # operationId resolves to *its* wire name correctly.
        out[short] = str(wire)
    if not out:
        _log.warning("wire_name_map(%s): no mcpTools published on API", server)
    return out
