"""
Eval harness for the MCP Tool Governance PoC.

For each (config, prompt) pair, runs N times against Azure OpenAI with the
config's MCP server tool catalog presented as OpenAI tool definitions, then
scores which tool the model picked.

Configs:
  A_messy     — messy-mcp/mcp        (anti-patterns, collisions, vague names)
  B_governed  — governed-mcp/mcp     (clean wire names + rich USE-WHEN/DO-NOT-USE)

Outputs:
  eval/results/runs.csv      — every (config, prompt, run) row with picked tool
  eval/results/summary.md    — per-config correct-tool rate + lift

Env vars (set or supply via .env):
  AOAI_ENDPOINT          e.g. https://common-open-ai.openai.azure.com
  AOAI_DEPLOYMENT        deployment name (default: gpt-4o-mini)
  AOAI_API_VERSION       default: 2024-10-21
  APIM_KEY               APIM subscription key
  APIM_BASE              e.g. https://apimopenai99.azure-api.net
  EVAL_RUNS              runs per prompt (default: 3)

Auth: Azure OpenAI via DefaultAzureCredential (your `az login`). No keys.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests
import yaml
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

ROOT = Path(__file__).parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

AOAI_ENDPOINT = os.environ.get("AOAI_ENDPOINT", "https://common-open-ai.openai.azure.com")
AOAI_DEPLOYMENT = os.environ.get("AOAI_DEPLOYMENT", "gpt-4o-mini")
AOAI_API_VERSION = os.environ.get("AOAI_API_VERSION", "2024-10-21")
APIM_BASE = os.environ.get("APIM_BASE", "https://apimopenai99.azure-api.net")
APIM_KEY = os.environ.get("APIM_KEY") or Path("/tmp/apim-master-key.txt").read_text().strip()
RUNS = int(os.environ.get("EVAL_RUNS", "3"))

CONFIGS = {
    "A_messy": f"{APIM_BASE}/messy-mcp/mcp",
    "B_governed": f"{APIM_BASE}/governed-mcp/mcp",
}

SYSTEM_PROMPT = (
    "You are a finance assistant. The user will ask a question. "
    "Pick exactly ONE tool from the available tools that best satisfies the request "
    "and call it with reasonable arguments. Do not call multiple tools. "
    "If no tool is suitable, respond with text only."
)


def mcp_tools_list(url: str) -> list[dict]:
    """Fetch tools/list from an MCP server."""
    r = requests.post(
        url,
        headers={
            "Ocp-Apim-Subscription-Key": APIM_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["result"]["tools"]


def mcp_tool_to_openai(t: dict) -> dict:
    """Translate an MCP tool descriptor to OpenAI's tool-call schema.

    OpenAI requires tool function names to match ^[a-zA-Z0-9_-]{1,64}$.
    MCP wire names already satisfy this; we still de-dup duplicate names by
    suffixing _2, _3, ... so the API doesn't reject the request.
    """
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": (t.get("description") or "")[:1024],
            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
        },
    }


def dedupe_tools(tools: list[dict]) -> list[dict]:
    seen: dict[str, int] = defaultdict(int)
    out: list[dict] = []
    for t in tools:
        name = t["function"]["name"]
        seen[name] += 1
        if seen[name] > 1:
            t = json.loads(json.dumps(t))
            t["function"]["name"] = f"{name}_{seen[name]}"
        out.append(t)
    return out


def _strip_unsupported_schema(schema: Any) -> Any:
    """Recursively drop JSON-Schema keywords that the OpenAI tool-call validator
    rejects (e.g. 'minimum', 'maximum', 'exclusiveMinimum', 'format' on some
    types). The model still gets the description, type, and required fields,
    which is what tool selection needs.
    """
    drop = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "multipleOf", "minLength", "maxLength", "pattern",
            "minItems", "maxItems", "uniqueItems"}
    if isinstance(schema, dict):
        return {k: _strip_unsupported_schema(v) for k, v in schema.items() if k not in drop}
    if isinstance(schema, list):
        return [_strip_unsupported_schema(v) for v in schema]
    return schema


def build_openai_client() -> AzureOpenAI:
    cred = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        cred, "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_version=AOAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )


def run_one(client: AzureOpenAI, tools: list[dict], prompt: str) -> tuple[str | None, float]:
    """Returns (picked_tool_name, latency_seconds). picked_tool_name is None
    if the model declined to call any tool."""
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=AOAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        tools=tools,
        tool_choice="auto",
        temperature=0,
    )
    dt = time.perf_counter() - t0
    msg = resp.choices[0].message
    if not msg.tool_calls:
        return None, dt
    picked = msg.tool_calls[0].function.name
    # un-dedupe: financeFoo_2 -> financeFoo
    picked = re.sub(r"_\d+$", "", picked)
    return picked, dt


def is_correct(config: str, picked: str | None, expected: str, acceptable: list[str]) -> bool:
    if picked is None:
        return False
    if config == "B_governed":
        return picked == expected
    # A_messy: any acceptable alias counts
    return picked in acceptable


def main() -> int:
    spec = yaml.safe_load((ROOT / "prompts.yaml").read_text())
    prompts = spec["prompts"]
    print(f"Loaded {len(prompts)} prompts; runs/prompt={RUNS}; deployment={AOAI_DEPLOYMENT}")

    client = build_openai_client()

    # Fetch + translate tool catalogs once per config.
    catalogs: dict[str, list[dict]] = {}
    for config, url in CONFIGS.items():
        raw = mcp_tools_list(url)
        translated = dedupe_tools([mcp_tool_to_openai(t) for t in raw])
        # Strip schema keywords AOAI rejects
        for t in translated:
            t["function"]["parameters"] = _strip_unsupported_schema(t["function"]["parameters"])
        catalogs[config] = translated
        print(f"  {config:12} {url}  ({len(raw)} raw -> {len(translated)} after dedupe)")

    runs_path = RESULTS / "runs.csv"
    with runs_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "prompt_id", "run", "expected", "picked", "correct", "latency_s"])

        totals: dict[str, list[bool]] = defaultdict(list)
        per_prompt: dict[tuple[str, str], list[bool]] = defaultdict(list)

        for config, tools in catalogs.items():
            for p in prompts:
                for run in range(1, RUNS + 1):
                    try:
                        picked, dt = run_one(client, tools, p["prompt"])
                    except Exception as e:
                        print(f"  [err] {config} {p['id']} run {run}: {e}", file=sys.stderr)
                        picked, dt = None, 0.0
                    correct = is_correct(config, picked, p["expected_canonical"],
                                         p.get("acceptable_messy") or [])
                    w.writerow([config, p["id"], run, p["expected_canonical"],
                                picked or "", correct, f"{dt:.3f}"])
                    totals[config].append(correct)
                    per_prompt[(config, p["id"])].append(correct)
                    print(f"  {config:12} {p['id']:14} run{run}  picked={picked!s:30} {'OK' if correct else 'X'}")

    # Summary
    summary = ["# Eval Summary", ""]
    summary.append(f"- Deployment: `{AOAI_DEPLOYMENT}`")
    summary.append(f"- Prompts: {len(prompts)}, runs/prompt: {RUNS}")
    summary.append(f"- Total invocations per config: {len(prompts) * RUNS}")
    summary.append("")
    summary.append("## Correct-tool rate")
    summary.append("")
    summary.append("| Config | Correct | Total | Rate |")
    summary.append("|---|---|---|---|")
    rates = {}
    for config, results in totals.items():
        ok = sum(results)
        n = len(results)
        rate = ok / n if n else 0.0
        rates[config] = rate
        summary.append(f"| `{config}` | {ok} | {n} | **{rate:.1%}** |")

    if "A_messy" in rates and "B_governed" in rates:
        lift = (rates["B_governed"] - rates["A_messy"]) * 100
        summary.append("")
        summary.append(f"**Absolute lift (governed − messy): {lift:+.1f} percentage points**")

    summary.append("")
    summary.append("## Per-prompt detail")
    summary.append("")
    summary.append("| Prompt | Expected | A_messy | B_governed |")
    summary.append("|---|---|---|---|")
    for p in prompts:
        a = per_prompt.get(("A_messy", p["id"]), [])
        b = per_prompt.get(("B_governed", p["id"]), [])
        a_str = f"{sum(a)}/{len(a)}" if a else "-"
        b_str = f"{sum(b)}/{len(b)}" if b else "-"
        summary.append(f"| `{p['id']}` | `{p['expected_canonical']}` | {a_str} | {b_str} |")

    (RESULTS / "summary.md").write_text("\n".join(summary) + "\n")
    print(f"\nWrote {runs_path} and {RESULTS/'summary.md'}")
    print("\n" + "\n".join(summary[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
