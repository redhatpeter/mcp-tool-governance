"""Deploy L3 policies to APIM (smoke variant).

Reads the production policy XML from apim/policies/, builds a merged
"smoke" variant per server (JWT + rate-limit commented out, server-name
substituted), and PUTs it to APIM.

Smoke variant differs from production only in:
  - <validate-jwt> commented out
  - <rate-limit-by-key> commented out
  - {{server-name}} placeholder replaced with the actual API name
  - Cosmos AAD via <authentication-managed-identity> (already in source)
    — relies on APIM's system-assigned MI having Cosmos data-plane read on
    /dbs/governance/colls/mcp-canonical-map.

Usage:
    az login   # the caller needs APIM contributor on the target APIM
    # optional: APIM_SUBSCRIPTION_ID / APIM_RESOURCE_GROUP / APIM_SERVICE_NAME
    python3 apim/deploy/deploy_l3_policies.py

Targets:
    .../apis/governed-mcp/policies/policy
    .../apis/messy-mcp/policies/policy
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POL_DIR = REPO_ROOT / "apim" / "policies"



def _current_subscription() -> str:
    out = subprocess.check_output(
        ["az", "account", "show", "--query", "id", "-o", "tsv"], text=True
    )
    return out.strip().replace("\r", "")


# Override with env vars to target a different APIM; the subscription
# defaults to the one selected by `az account set`.
SUBSCRIPTION_ID = os.environ.get("APIM_SUBSCRIPTION_ID") or _current_subscription()
RESOURCE_GROUP = os.environ.get("APIM_RESOURCE_GROUP", "rg_apim")
APIM_NAME = os.environ.get("APIM_SERVICE_NAME", "apimopenai992")
API_VERSION = "2025-03-01-preview"

TARGETS = ["governed-mcp", "messy-mcp"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_jwt_and_ratelimit(xml: str) -> str:
    """Comment out <validate-jwt …>…</validate-jwt> and
    <rate-limit-by-key … /> for the smoke variant."""
    # Multi-line validate-jwt block
    xml = re.sub(
        r"(<validate-jwt\b[\s\S]*?</validate-jwt>)",
        r"<!-- SMOKE: jwt disabled\n\1\n-->",
        xml,
    )
    # Self-closing rate-limit-by-key (multi-line attrs)
    xml = re.sub(
        r"(<rate-limit-by-key\b[\s\S]*?/>)",
        r"<!-- SMOKE: rate-limit disabled\n\1\n-->",
        xml,
    )
    return xml


def _extract_inbound_body(xml: str) -> str:
    """Return the contents of <inbound>…</inbound> WITHOUT the wrapping
    tags or the leading <base />. The caller will splice it after the
    outer policy's own <base />."""
    m = re.search(r"<inbound>([\s\S]*?)</inbound>", xml)
    if not m:
        raise RuntimeError("no <inbound> block")
    body = m.group(1)
    # Drop leading <base /> (we'll provide one in the merged policy)
    body = re.sub(r"^\s*<base\s*/>\s*", "", body, count=1)
    return body.strip()


def _extract_outbound_body(xml: str) -> str:
    m = re.search(r"<outbound>([\s\S]*?)</outbound>", xml)
    if not m:
        raise RuntimeError("no <outbound> block")
    body = m.group(1)
    body = re.sub(r"^\s*<base\s*/>\s*", "", body, count=1)
    return body.strip()


def _strip_comments(xml: str) -> str:
    return re.sub(r"<!--[\s\S]*?-->", "", xml)


def build_merged_policy(server_name: str) -> str:
    rewrite = _read(POL_DIR / "canonical-rewrite.policy.xml")
    rewrite = _strip_jwt_and_ratelimit(rewrite)
    # Strip comments BEFORE extracting <inbound>/<outbound> — otherwise
    # the regex can match `<outbound>` tokens that appear inside doc
    # comments and grab the wrong block.
    rewrite = _strip_comments(rewrite)
    rewrite = rewrite.replace("{{server-name}}", server_name)

    filter_xml = _read(POL_DIR / "tools-list-filter.policy.xml")
    filter_xml = _strip_comments(filter_xml)
    filter_xml = filter_xml.replace("{{server-name}}", server_name)

    inbound_body = _extract_inbound_body(rewrite)
    # Merge BOTH outbounds: the rewrite policy emits the
    # `x-mcp-canonical-rewrite` response header from <outbound> (because
    # set-header in <inbound> targets the request, not the response), and
    # the filter policy does the tools/list filtering. Order matters only
    # for shared variables — these two don't overlap.
    rewrite_outbound = _extract_outbound_body(rewrite)
    filter_outbound = _extract_outbound_body(filter_xml)
    outbound_body = (rewrite_outbound + "\n\n" + filter_outbound).strip()

    merged = f"""<policies>
  <inbound>
    <base />
{inbound_body}
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
{outbound_body}
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
"""
    # Collapse runs of blank lines from comment removal.
    merged = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", merged)
    return merged.lstrip()


def get_token() -> str:
    out = subprocess.check_output(
        ["az", "account", "get-access-token", "--query", "accessToken", "-o", "tsv"],
        text=True,
    )
    return out.strip().replace("\r", "")


def put_policy(api_name: str, policy_xml: str) -> None:
    token = get_token()
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.ApiManagement/service/{APIM_NAME}"
        f"/apis/{api_name}/policies/policy?api-version={API_VERSION}"
    )
    payload = {
        "properties": {
            "format": "rawxml",
            "value": policy_xml,
        }
    }
    body = json.dumps(payload)
    cmd = [
        "curl", "-s", "-X", "PUT", url,
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", body,
    ]
    out = subprocess.check_output(cmd, text=True)
    # When format=rawxml is requested, APIM PUT returns the stored XML on
    # success and a JSON {"error": ...} on failure.
    stripped = out.lstrip("\ufeff").lstrip()
    if stripped.startswith("<"):
        print(f"[{api_name}] OK (XML response, {len(out)} chars stored)")
        return
    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        print(f"[{api_name}] unexpected response (first 300 chars): {out[:300]}")
        sys.exit(1)
    if "error" in resp:
        print(f"[{api_name}] FAIL: {resp['error']}")
        sys.exit(1)
    print(f"[{api_name}] OK — etag={resp.get('etag')}")


def main() -> int:
    out_dir = REPO_ROOT / "apim" / "deploy" / "_built"
    out_dir.mkdir(parents=True, exist_ok=True)
    for srv in TARGETS:
        merged = build_merged_policy(srv)
        local = out_dir / f"{srv}.policy.xml"
        local.write_text(merged, encoding="utf-8")
        print(f"[{srv}] built {len(merged)} chars → {local.relative_to(REPO_ROOT)}")
        put_policy(srv, merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
