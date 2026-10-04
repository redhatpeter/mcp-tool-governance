"""MCP Tool Governance — Demo Frontend (Streamlit, Option A).

A single-process Streamlit UI that makes the value of the three governance
layers visible in <60 seconds:

  Tab 1 — "Headline":   side-by-side agent answer (messy vs governed) for the
                        same prompt; shows which tool got picked, latency,
                        correctness vs expected, response headers, and a
                        running session-wide tally.
  Tab 2 — "Catalog":    side-by-side tools/list snapshots with collision and
                        missing-description badges; demonstrates that
                        tools-list-filter dropped the alias entries on the
                        governed surface.
  Tab 3 — "L3 Rewrite": three preset alias names → tools/call → renders the
                        x-mcp-canonical-rewrite response header lighting up.
  Tab 4 — "L2 Sim":     paste-a-tool-description widget that POSTs to the
                        local dup-resolver /similarity endpoint and renders
                        DUPLICATE / WARN / REVIEW / OK with the nearest match.

Everything is self-contained (no import from eval/) so this file is what a
new engineer reads to understand "how do you actually call the gateway."

Run:
    cd frontend
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    # APIM master key on disk OR set APIM_KEY env var:
    #   az rest --method post --url ".../subscriptions/master/listSecrets?..." \
    #     --query primaryKey -o tsv > /tmp/apim-master-key.txt
    streamlit run app.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
import streamlit as st
import yaml
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Config (overridable via env)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_PATH = REPO_ROOT / "eval" / "prompts.yaml"

# Load frontend/.env (does not override pre-set env vars)
load_dotenv(Path(__file__).resolve().parent / ".env")

APIM_BASE = os.environ.get("APIM_BASE", "https://apimopenai992.azure-api.net")
APIM_KEY_FILE = os.environ.get("APIM_KEY_FILE", "/tmp/apim-master-key.txt")
AOAI_ENDPOINT = os.environ.get("AOAI_ENDPOINT", "https://common-open-ai2.openai.azure.com")
AOAI_DEPLOYMENT = os.environ.get("AOAI_DEPLOYMENT", "gpt-4.1-mini")
AOAI_API_VERSION = os.environ.get("AOAI_API_VERSION", "2024-10-21")
RESOLVER_URL = os.environ.get("RESOLVER_URL", "http://127.0.0.1:8089")
MAX_TURNS = int(os.environ.get("EVAL_MAX_TURNS", "3"))

CONFIGS = {
    "messy": f"{APIM_BASE}/messy-mcp/mcp",
    "governed": f"{APIM_BASE}/governed-mcp/mcp",
}

SYSTEM_PROMPT = (
    "You are a finance assistant. The user will ask a question. "
    "Pick exactly ONE tool from the available tools that best satisfies the request "
    "and call it with reasonable arguments. Do not call multiple tools in parallel. "
    "If no tool is suitable, respond with text only."
)


# ---------------------------------------------------------------------------
# Auth + clients (cached for the lifetime of the Streamlit process)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_apim_key() -> str:
    if os.environ.get("APIM_KEY"):
        return os.environ["APIM_KEY"].strip()
    p = Path(APIM_KEY_FILE)
    if p.exists():
        return p.read_text().strip()
    raise RuntimeError(
        f"No APIM key found. Set APIM_KEY env var or place the key at {APIM_KEY_FILE}."
    )


@st.cache_resource(show_spinner=False)
def get_openai_client() -> AzureOpenAI:
    cred = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        cred, "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_version=AOAI_API_VERSION,
        azure_ad_token_provider=token_provider,
    )


# ---------------------------------------------------------------------------
# MCP wire (tools/list, tools/call) + OpenAI tool translation
# ---------------------------------------------------------------------------

def _mcp_post(url: str, payload: dict, *, timeout: int = 20) -> dict:
    """POST a JSON-RPC frame to an MCP endpoint and return the parsed body.

    APIM-MCP returns either application/json or text/event-stream depending on
    Accept negotiation. We request both and parse whichever comes back.
    """
    r = requests.post(
        url,
        headers={
            "Ocp-Apim-Subscription-Key": get_apim_key(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json=payload,
        timeout=timeout,
    )
    r.raise_for_status()
    text = r.text
    if "data:" in text:
        # SSE frame: pull the first data: payload
        text = re.sub(r"^.*?data:\s*", "", text, count=1, flags=re.S).strip()
    return json.loads(text), dict(r.headers)


@st.cache_data(ttl=60, show_spinner=False)
def mcp_tools_list(url: str) -> tuple[list[dict], dict]:
    body, headers = _mcp_post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return body.get("result", {}).get("tools", []) or [], headers


def mcp_tools_call(url: str, name: str, args: dict | None = None) -> tuple[dict, dict]:
    body, headers = _mcp_post(url, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args or {}},
    })
    return body, headers


def mcp_tool_to_openai(t: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": (t.get("description") or "")[:1024],
            "parameters": _strip_unsupported_schema(
                t.get("inputSchema") or {"type": "object", "properties": {}}
            ),
        },
    }


def dedupe_tools(tools: list[dict]) -> list[dict]:
    """OpenAI rejects duplicate function names; suffix _2, _3 ... when seen."""
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
    """Drop JSON-Schema keywords that Azure OpenAI's tool validator rejects."""
    drop = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "multipleOf", "minLength", "maxLength", "pattern",
            "minItems", "maxItems", "uniqueItems"}
    if isinstance(schema, dict):
        return {k: _strip_unsupported_schema(v) for k, v in schema.items() if k not in drop}
    if isinstance(schema, list):
        return [_strip_unsupported_schema(v) for v in schema]
    return schema


# ---------------------------------------------------------------------------
# Multi-turn agent loop (mirrors eval/run_eval.py::run_one)
# ---------------------------------------------------------------------------

def _synthetic_tool_result(name: str) -> str:
    """Plausible JSON the model can pull ids from to plan a follow-up call."""
    return json.dumps({
        "customer_id": "cust-42",
        "customers": [
            {"customer_id": "cust-42", "name": "Acme Corp", "tier": "gold",
             "email": "ops@acme.example.com"}
        ],
        "invoice_id": "inv-1001",
        "invoices": [
            {"invoice_id": "inv-1001", "customer_id": "cust-42",
             "amount": 1234.50, "status": "sent"}
        ],
        "_demo_note": f"synthetic result for {name}",
    })


def run_agent(
    client: AzureOpenAI, tools: list[dict], prompt: str,
    max_turns: int = MAX_TURNS,
) -> dict[str, Any]:
    """Run the agent loop and return what the demo needs to render.

    Returns dict: picked (list[str]), latency_s (float), declined (bool),
    final_text (str | None) — model's text reply if it declined to use tools.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    picked: list[str] = []
    final_text: str | None = None
    t0 = time.perf_counter()
    for _turn in range(max_turns):
        resp = client.chat.completions.create(
            model=AOAI_DEPLOYMENT,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final_text = msg.content
            break
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            name = re.sub(r"_\d+$", "", tc.function.name)
            picked.append(name)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": _synthetic_tool_result(name),
            })
    return {
        "picked": picked,
        "latency_s": time.perf_counter() - t0,
        "declined": not picked,
        "final_text": final_text,
    }


# ---------------------------------------------------------------------------
# Tools-list quality scoring (for the catalog tab)
# ---------------------------------------------------------------------------

def score_catalog(tools: list[dict]) -> dict[str, Any]:
    names = [t["name"] for t in tools]
    name_counts: dict[str, int] = defaultdict(int)
    for n in names:
        name_counts[n] += 1
    collisions = {n: c for n, c in name_counts.items() if c > 1}
    no_desc = [t["name"] for t in tools if len((t.get("description") or "").strip()) < 10]
    return {
        "total": len(tools),
        "unique_names": len(set(names)),
        "collisions": collisions,
        "no_desc": no_desc,
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_prompts() -> list[dict]:
    return yaml.safe_load(PROMPTS_PATH.read_text())["prompts"]


# ===========================================================================
# UI
# ===========================================================================

st.set_page_config(
    page_title="MCP Tool Governance — Demo",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state for the running tally
if "tally" not in st.session_state:
    st.session_state.tally = {"messy": [], "governed": []}  # list[bool]

# ---- Sidebar ----
with st.sidebar:
    st.markdown("### MCP Tool Governance")
    st.caption("Demo frontend (Option A — Streamlit)")

    st.markdown("**Endpoints**")
    st.code(f"messy:    {CONFIGS['messy']}\ngoverned: {CONFIGS['governed']}", language="text")
    st.caption(f"Resolver: `{RESOLVER_URL}`")
    st.caption(f"Model: `{AOAI_DEPLOYMENT}` @ `{AOAI_ENDPOINT}`")

    # Auth health
    try:
        _ = get_apim_key()
        st.success("✓ APIM key loaded")
    except Exception as e:
        st.error(f"✗ APIM key missing: {e}")

    st.markdown("---")
    if st.button("Reset session tally", use_container_width=True):
        st.session_state.tally = {"messy": [], "governed": []}
        st.rerun()

    st.markdown("---")
    st.caption("Built from `eval/run_eval.py` + `eval/prompts.yaml`. "
               "See [`docs/ARCHITECTURE.md`](https://github.com/redhatpeter/mcp-tool-governance/blob/main/docs/ARCHITECTURE.md) for the full design.")


# ---- Title + sticky scoreboard ----
st.title("MCP Tool Governance — Live Demo")
tally = st.session_state.tally
m_ok, m_n = sum(tally["messy"]), len(tally["messy"])
g_ok, g_n = sum(tally["governed"]), len(tally["governed"])
c1, c2, c3 = st.columns(3)
c1.metric("Messy MCP — correct picks", f"{m_ok}/{m_n}", f"{(m_ok/m_n*100 if m_n else 0):.0f}%")
c2.metric("Governed MCP — correct picks", f"{g_ok}/{g_n}", f"{(g_ok/g_n*100 if g_n else 0):.0f}%")
lift = ((g_ok/g_n) - (m_ok/m_n)) * 100 if (m_n and g_n) else 0
c3.metric("Lift (governed − messy)", f"{lift:+.0f} pp",
          help="Per-prompt-pair lift across this session.")

st.markdown("---")

tab_headline, tab_catalog, tab_l3, tab_l2 = st.tabs([
    "🎯 Headline (run a prompt)",
    "📋 Tool catalog (side-by-side)",
    "🔁 L3 — runtime rewrite",
    "🧠 L2 — semantic dup check",
])

# ---------------------------------------------------------------------------
# TAB 1 — Headline
# ---------------------------------------------------------------------------
with tab_headline:
    prompts = load_prompts()
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for p in prompts:
        by_cat[p.get("category", "Other")].append(p)

    st.markdown("**Pick a sample prompt** — it goes to **both** servers, agents pick a tool, you see who's right.")
    cats = ["⭐ Headline only"] + sorted(by_cat.keys())
    cat = st.selectbox("Category", cats, index=0, key="cat_select")

    pool = (
        [p for p in prompts if p.get("demo_priority") == "high"]
        if cat.startswith("⭐") else by_cat[cat]
    )
    labels = [
        f"{'⭐ ' if p.get('demo_priority') == 'high' else ''}{p['id']:14s} — {p['prompt']}"
        for p in pool
    ]
    pick_idx = st.radio(
        "Sample prompt",
        list(range(len(pool))),
        format_func=lambda i: labels[i],
        index=0, key="prompt_radio",
    )
    chosen = pool[pick_idx]
    if chosen.get("narrator_note"):
        st.info(f"💡 **Narrator:** {chosen['narrator_note']}")

    # Key the textbox by the chosen prompt id so it resets to the new prompt
    # whenever the radio changes. Without this, Streamlit's widget cache holds
    # whatever was previously typed/selected — leading the agent to run
    # against the wrong prompt and produce misleading verdicts.
    user_prompt = st.text_area(
        "Prompt to send (edit if you like)",
        value=chosen["prompt"], height=70,
        key=f"prompt_text__{chosen['id']}",
    )

    run = st.button("▶  Run on both servers in parallel", type="primary", use_container_width=True)

    if run:
        try:
            client = get_openai_client()
            with st.spinner("Fetching tool catalogs from both gateways..."):
                catalogs: dict[str, list[dict]] = {}
                for cfg, url in CONFIGS.items():
                    raw, _hdr = mcp_tools_list(url)
                    catalogs[cfg] = dedupe_tools([mcp_tool_to_openai(t) for t in raw])
        except Exception as e:
            st.error(f"Could not fetch tools/list: {e}")
            st.stop()

        with st.spinner(f"Running agent on both servers (max {MAX_TURNS} turns each)..."):
            with ThreadPoolExecutor(max_workers=2) as ex:
                futs = {cfg: ex.submit(run_agent, client, catalogs[cfg], user_prompt)
                        for cfg in CONFIGS}
                results = {cfg: futs[cfg].result() for cfg in CONFIGS}

        expected = chosen["expected_canonical"]
        acceptable = chosen.get("acceptable_messy") or []

        # Update the running tally so the scoreboard at the top refreshes.
        for cfg in CONFIGS:
            picked = results[cfg]["picked"]
            if cfg == "governed":
                correct = expected in picked
            else:
                correct = any(p in acceptable for p in picked)
            st.session_state.tally[cfg].append(correct)

        # Persist this run's result so it survives the rerun below
        # (st.rerun() refreshes the top scoreboard but otherwise wipes the
        # `if run:` block — render the per-server panel from session_state
        # OUTSIDE this block so it stays visible).
        st.session_state.last_run = {
            "results": results,
            "expected": expected,
            "acceptable": acceptable,
            "catalog_sizes": {k: len(v) for k, v in catalogs.items()},
            "prompt_id": chosen["id"],
            "prompt_text": user_prompt,
        }
        st.rerun()  # refresh top scoreboard

    # Render the most recent run's per-server panel (persists across reruns).
    last = st.session_state.get("last_run")
    if last:
        expected = last["expected"]
        acceptable = last["acceptable"]
        results = last["results"]
        catalog_sizes = last["catalog_sizes"]
        st.markdown(f"##### Last run: `{last['prompt_id']}` — _{last['prompt_text']}_")
        col_m, col_g = st.columns(2, gap="medium")
        for col, cfg, header in [(col_m, "messy", "Messy MCP"), (col_g, "governed", "Governed MCP")]:
            with col:
                st.markdown(f"#### {header}")
                r = results[cfg]
                picked = r["picked"]
                if cfg == "governed":
                    correct = expected in picked
                else:
                    correct = any(p in acceptable for p in picked)
                badge = "✅ Correct" if correct else ("❌ Wrong tool" if picked else "⚠️ Declined")
                st.markdown(f"**Verdict:** {badge}")
                if picked:
                    st.markdown("**Tool chain:** " + " → ".join(f"`{p}`" for p in picked))
                else:
                    st.markdown("**Tool chain:** _(no tool called — model declined)_")
                    if r["final_text"]:
                        with st.expander("Model's text reply"):
                            st.write(r["final_text"])
                st.metric("Latency", f"{r['latency_s']*1000:.0f} ms")
                st.caption(
                    f"Catalog size: **{catalog_sizes[cfg]}** tools · "
                    f"Expected (governed scoring): `{expected}` · "
                    f"Acceptable on messy: {', '.join(f'`{a}`' for a in acceptable) or '_none_'}"
                )

# ---------------------------------------------------------------------------
# TAB 2 — Tool catalog side-by-side
# ---------------------------------------------------------------------------
with tab_catalog:
    st.markdown("**Live `tools/list` from each MCP server.** "
                "Watch the totals — the governed server's `tools-list-filter` "
                "policy drops alias entries on the wire.")
    if st.button("🔄 Refresh catalogs"):
        mcp_tools_list.clear()
        st.rerun()

    try:
        with st.spinner("Calling tools/list on both gateways..."):
            messy_tools, m_hdr = mcp_tools_list(CONFIGS["messy"])
            governed_tools, g_hdr = mcp_tools_list(CONFIGS["governed"])
    except Exception as e:
        st.error(f"tools/list failed: {e}")
        st.stop()

    col_m, col_g = st.columns(2, gap="medium")
    for col, name, tools, hdr in [
        (col_m, "Messy MCP", messy_tools, m_hdr),
        (col_g, "Governed MCP", governed_tools, g_hdr),
    ]:
        with col:
            score = score_catalog(tools)
            st.markdown(f"### {name}")
            st.metric("Tools exposed", score["total"])
            cols = st.columns(2)
            cols[0].metric("Wire-name collisions", len(score["collisions"]),
                           help="Duplicate function names — APIM-MCP silently drops dupes.")
            cols[1].metric("Missing/short description", len(score["no_desc"]))
            x_filtered = hdr.get("x-mcp-tools-filtered") or hdr.get("X-Mcp-Tools-Filtered")
            if x_filtered:
                st.success(f"Gateway dropped **{x_filtered}** alias tool(s) via tools-list-filter policy.")
            if score["collisions"]:
                with st.expander(f"Collisions ({len(score['collisions'])})"):
                    for n, c in score["collisions"].items():
                        st.write(f"- `{n}` × {c}")
            if score["no_desc"]:
                with st.expander(f"Missing description ({len(score['no_desc'])})"):
                    for n in score["no_desc"]:
                        st.write(f"- `{n}`")
            with st.expander(f"Full tool list ({score['total']})"):
                for t in sorted(tools, key=lambda x: x["name"]):
                    desc = (t.get("description") or "").strip()
                    st.markdown(f"**`{t['name']}`** — {desc[:200] or '_(no description)_'}")

# ---------------------------------------------------------------------------
# TAB 3 — L3 runtime rewrite
# ---------------------------------------------------------------------------
with tab_l3:
    st.markdown("**Runtime canonical rewrite.** Same call to the same gateway with three different tool names. "
                "Watch the `x-mcp-canonical-rewrite` response header.")

    cases = [
        ("Test A", "financeQuoteGet",
         "Already-canonical name. Gateway no-ops."),
        ("Test B", "get_finance_quote",
         "Legacy snake_case alias. Gateway looks up Cosmos and rewrites the JSON-RPC body."),
        ("Test C", "fetch_quote",
         "Different team's naming. Same canonical underneath — federated tool catalog without breaking anyone."),
    ]
    cols = st.columns(3, gap="medium")
    for col, (label, name, blurb) in zip(cols, cases):
        with col:
            st.markdown(f"#### {label}")
            st.caption(f"Requested: `{name}`")
            st.caption(blurb)
            if st.button(f"▶ Send `{name}`", key=f"l3_{name}", use_container_width=True):
                try:
                    body, hdr = mcp_tools_call(
                        CONFIGS["governed"], name, {"symbol": "MSFT"},
                    )
                except Exception as e:
                    st.error(str(e)); continue
                rewrite = hdr.get("x-mcp-canonical-rewrite") or hdr.get("X-Mcp-Canonical-Rewrite")
                if rewrite:
                    if "->" in rewrite or "→" in rewrite:
                        st.success(f"✨ rewrite: `{rewrite}`")
                    else:
                        st.info(f"`x-mcp-canonical-rewrite: {rewrite}`")
                else:
                    st.warning("No `x-mcp-canonical-rewrite` header in response.")
                with st.expander("Raw JSON-RPC response"):
                    st.json(body)
                with st.expander("All response headers"):
                    st.json({k: v for k, v in hdr.items()
                             if k.lower().startswith(("x-", "content-", "ms-"))})

# ---------------------------------------------------------------------------
# TAB 4 — L2 similarity
# ---------------------------------------------------------------------------
with tab_l2:
    st.markdown("**Pre-merge duplicate detection.** Paste a tool description as if it just landed in a PR. "
                "We embed it with `text-embedding-3-large` and vector-query the live AI Search index.")
    st.caption(f"Resolver: `{RESOLVER_URL}` — start with: "
               "`cd apps/dup-resolver && uvicorn main:app --port 8089`")

    name = st.text_input("Proposed tool name", value="financeQuoteFetch")
    description = st.text_area(
        "Proposed description",
        value="Fetch a real-time stock quote for a given ticker symbol.",
        height=80,
    )

    cols = st.columns([1, 1, 2])
    do_check = cols[0].button("🧠 Check similarity", type="primary", use_container_width=True)
    do_clusters = cols[1].button("📊 Show all clusters", use_container_width=True)

    if do_check:
        try:
            r = requests.post(
                f"{RESOLVER_URL}/similarity",
                json={"name": name, "description": description},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            st.error(f"Resolver call failed: {e}"); st.stop()

        v = data.get("verdict", "?")
        cmap = {"DUPLICATE": "error", "WARN": "warning", "REVIEW": "info", "OK": "success"}
        getattr(st, cmap.get(v, "info"))(f"**{v}** — {data.get('reason', '')}")
        if data.get("nearest"):
            st.markdown("**Nearest matches:**")
            for h in data["nearest"][:5]:
                marker = " ★ canonical" if h.get("is_canonical") else ""
                st.markdown(
                    f"- `{h.get('server', '?')}/{h.get('name', '?')}` "
                    f"— score **{h.get('score', 0):.3f}**{marker}"
                )
        with st.expander("Raw resolver response"):
            st.json(data)

    if do_clusters:
        try:
            r = requests.get(f"{RESOLVER_URL}/clusters", timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            st.error(f"Resolver call failed: {e}"); st.stop()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total tools", data.get("total_tools", 0))
        c2.metric("Total clusters", data.get("total_clusters", 0))
        c3.metric("Multi-member clusters", data.get("duplicates", 0))
        multi = [c for c in data.get("clusters", []) if len(c.get("members", [])) > 1]
        if multi:
            st.markdown("**Semantic-duplicate clusters:**")
            for c in multi:
                st.markdown(f"#### `{c['cluster_id']}` — canonical: `{c['canonical']}`")
                for m in c["members"]:
                    star = " ★" if m.get("is_canonical") else ""
                    st.markdown(f"  - `{m.get('server')}/{m.get('name')}`{star}")
        with st.expander("Raw clusters payload"):
            st.json(data)
