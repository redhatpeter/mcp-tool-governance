"""Pull tools/list from each configured APIM-MCP server."""
from __future__ import annotations

import httpx

import config
from fingerprint import ToolDescriptor


def _post(url: str, key: str, body: dict) -> dict:
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    with httpx.Client(timeout=20.0) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        # Some APIM-MCP responses are SSE-framed; strip if so
        text = r.text
        if text.lstrip().startswith("event:"):
            # Find the data: payload
            for line in text.splitlines():
                if line.startswith("data:"):
                    import json
                    return json.loads(line[len("data:"):].strip())
        return r.json()


def fetch_tools(server: str) -> list[ToolDescriptor]:
    url = f"{config.APIM_GATEWAY_BASE}/{server}/mcp"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    resp = _post(url, config.apim_subscription_key(), body)
    tools = (resp.get("result") or {}).get("tools") or []
    out: list[ToolDescriptor] = []
    for t in tools:
        out.append(ToolDescriptor(
            server=server,
            name=str(t.get("name") or ""),
            description=str(t.get("description") or ""),
            input_schema=t.get("inputSchema") or {},
        ))
    return out


def fetch_all() -> list[ToolDescriptor]:
    out: list[ToolDescriptor] = []
    for s in config.MCP_SERVERS:
        out.extend(fetch_tools(s))
    return out
