"""L1 PR similarity check.

Given a list of OpenAPI files and a git base ref, diff to find newly
introduced operationIds, build a synthetic ToolDescriptor for each, and
score it against the live AI Search index using the same logic as the
``/similarity`` endpoint.

Output:
* A markdown report on stdout (suitable for ``$GITHUB_STEP_SUMMARY``)
* Exit code 1 if any DUPLICATE verdicts are found, else 0

Usage::

    python check_pr.py --base origin/main apim/openapi/finance-governed.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import config
import embed
import fingerprint as fp
import openapi_source
import search_client


# ---------------------------------------------------------------------------
# OpenAPI extraction
# ---------------------------------------------------------------------------

def extract_operations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``{operationId: {summary, description, path, method}}``."""
    out: dict[str, dict[str, Any]] = {}
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId")
            if not op_id:
                continue
            out[op_id] = {
                "summary": op.get("summary") or "",
                "description": op.get("description") or "",
                "path": path,
                "method": method,
            }
    return out


def load_spec_at_ref(ref: str, path: str) -> dict[str, Any] | None:
    """Read an OpenAPI file at a given git ref. Returns None if absent."""
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _load_head_spec(file_path: str) -> dict[str, Any]:
    """Read a working-tree OpenAPI file with friendly errors (no traceback)."""
    p = Path(file_path)
    if not p.exists():
        print(f"ERROR: spec file not found: {file_path}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: {file_path} is not valid JSON: {e.msg} "
              f"(line {e.lineno}, col {e.colno})", file=sys.stderr)
        sys.exit(2)


def diff_new_operations(base_ref: str, file_path: str) -> list[dict[str, Any]]:
    """Return operations present in the working tree but not in ``base_ref``."""
    head_spec = _load_head_spec(file_path)
    head_ops = extract_operations(head_spec)
    base_spec = load_spec_at_ref(base_ref, file_path)
    base_ops = extract_operations(base_spec) if base_spec else {}
    new = []
    for op_id, info in head_ops.items():
        if op_id in base_ops:
            continue
        new.append({"operationId": op_id, "spec_file": file_path, **info})
    return new


def diff_deleted_operations(base_ref: str, file_path: str) -> set[str]:
    """Return operationIds removed in the working tree relative to ``base_ref``.

    Used to mute false-positive DUPLICATE verdicts during a rename PR: if the
    new op matches an op we're deleting in the same PR, it's a rename, not a
    real duplicate.
    """
    head_spec = _load_head_spec(file_path)
    head_ops = extract_operations(head_spec)
    base_spec = load_spec_at_ref(base_ref, file_path)
    if not base_spec:
        return set()
    base_ops = extract_operations(base_spec)
    return set(base_ops) - set(head_ops)


def _server_for_spec(spec_file: str) -> str | None:
    """Map a spec file path to its MCP server name (mirror openapi_source)."""
    stem = Path(spec_file).stem
    return openapi_source.SERVER_BY_FILE.get(stem)


# ---------------------------------------------------------------------------
# Similarity scoring (mirrors main.py /similarity logic)
# ---------------------------------------------------------------------------

def score_candidate(op: dict[str, Any],
                    deleted_in_pr: dict[str, set[str]] | None = None) -> dict[str, Any]:
    """Score a single candidate operation against the live index.

    ``deleted_in_pr`` is ``{server: {operationIds_being_deleted}}`` for the
    same PR. If the top match is one of those, we treat the verdict as a
    rename (INFO), not a duplicate.
    """
    desc = op.get("description") or op.get("summary") or ""
    descriptor = fp.ToolDescriptor(
        server="<pr-candidate>",
        name=op["operationId"],
        description=desc,
        input_schema={},
    )
    text = fp.fingerprint_text(descriptor)
    vec = embed.embed_one(text)
    hits = search_client.vector_query(vec, k=5, select=[
        "id", "server", "tool_name", "cluster_id", "canonical_id", "is_canonical", "last_seen_utc",
    ])
    threshold = config.CLUSTER_THRESHOLD
    if not hits:
        verdict = "OK"
        reason = "index empty — no candidates to compare against"
    else:
        top = hits[0]
        score = float(top.get("_score", 0.0))
        # Rename detection: top match is being deleted in this same PR
        top_server = top.get("server")
        top_name = top.get("tool_name")
        is_rename = (
            deleted_in_pr is not None
            and top_server in deleted_in_pr
            and top_name in deleted_in_pr[top_server]
        )
        if is_rename:
            verdict = "INFO"
            reason = (
                f"top match '{top_name}' on {top_server} (score {score:.3f}) "
                f"is being deleted in this PR — looks like a rename, not a duplicate"
            )
        elif score >= threshold:
            verdict = "DUPLICATE"
            reason = (
                f"top match '{top['tool_name']}' on {top['server']} "
                f"(score {score:.3f}) >= threshold {threshold}; "
                f"reuse the canonical or rename this op"
            )
        elif score >= threshold - 0.05:
            verdict = "WARN"
            reason = (
                f"top match '{top['tool_name']}' (score {score:.3f}) "
                f"is close to threshold {threshold}; reviewer should confirm"
            )
        else:
            verdict = "OK"
            reason = f"no near-duplicates (top score {score:.3f} < {threshold})"
    return {
        "operationId": op["operationId"],
        "spec_file": op["spec_file"],
        "verdict": verdict,
        "reason": reason,
        "top_last_seen_utc": (hits[0].get("last_seen_utc") if hits else None),
        "nearest": [
            {
                "server": h.get("server"),
                "name": h.get("tool_name"),
                "score": round(float(h.get("_score", 0.0)), 4),
                "canonical_id": h.get("canonical_id"),
                "is_canonical": h.get("is_canonical"),
            }
            for h in hits[:3]
        ],
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

VERDICT_EMOJI = {"DUPLICATE": "🛑", "WARN": "⚠️", "OK": "✅", "INFO": "ℹ️"}


def render_report(results: list[dict[str, Any]]) -> str:
    if not results:
        return "## L1 similarity check\n\nNo new operations introduced — nothing to score.\n"
    lines = ["## L1 similarity check", ""]
    summary = {"DUPLICATE": 0, "WARN": 0, "OK": 0, "INFO": 0}
    for r in results:
        summary[r["verdict"]] += 1
    lines.append(
        f"**{len(results)} new operation(s) scored** — "
        f"🛑 {summary['DUPLICATE']} duplicate · "
        f"⚠️ {summary['WARN']} warn · "
        f"✅ {summary['OK']} ok"
        + (f" · ℹ️ {summary['INFO']} rename" if summary['INFO'] else "")
    )
    lines.append("")
    lines.append("| Verdict | operationId | Top match | Score | Reason |")
    lines.append("|---|---|---|---|---|")
    # Track index freshness for the footer.
    freshness = [r.get("top_last_seen_utc") for r in results if r.get("top_last_seen_utc")]
    for r in results:
        emo = VERDICT_EMOJI[r["verdict"]]
        top = r["nearest"][0] if r["nearest"] else {}
        top_str = f"{top.get('server','—')}/{top.get('name','—')}" if top else "—"
        score_str = f"{top.get('score', 0):.3f}" if top else "—"
        lines.append(
            f"| {emo} {r['verdict']} | `{r['operationId']}` | `{top_str}` | {score_str} | {r['reason']} |"
        )
    if freshness:
        # Min freshness = oldest top-hit observed; helps reviewers spot a stale index.
        oldest = min(freshness)
        lines.append("")
        lines.append(
            f"_Index freshness: oldest top-hit `last_seen_utc` = {oldest} "
            f"(re-run `ingest-on-merge` workflow if this looks stale)._"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main",
                    help="git ref to diff against (default: origin/main)")
    ap.add_argument("--all", action="store_true",
                    help="check ALL operations in the given files (not just new ones)")
    ap.add_argument("files", nargs="+", help="OpenAPI files to check")
    args = ap.parse_args()

    candidates: list[dict[str, Any]] = []
    # Build per-server set of ops being deleted in this PR. With --all we
    # have no diff context, so deletions are unknown (empty).
    deleted_in_pr: dict[str, set[str]] = {}
    for f in args.files:
        if args.all:
            spec = _load_head_spec(f)
            ops = extract_operations(spec)
            for op_id, info in ops.items():
                candidates.append({"operationId": op_id, "spec_file": f, **info})
        else:
            candidates.extend(diff_new_operations(args.base, f))
            server = _server_for_spec(f)
            if server:
                deleted = diff_deleted_operations(args.base, f)
                if deleted:
                    deleted_in_pr.setdefault(server, set()).update(deleted)

    print(f"# {len(candidates)} candidate operation(s) to score", file=sys.stderr)
    results = [score_candidate(c, deleted_in_pr=deleted_in_pr) for c in candidates]
    report = render_report(results)
    print(report)

    has_dup = any(r["verdict"] == "DUPLICATE" for r in results)
    return 1 if has_dup else 0


if __name__ == "__main__":
    sys.exit(main())
