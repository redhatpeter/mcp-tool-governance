"""Precision/recall threshold sweep over a labeled pair set.

Reads ``tests/labeled_pairs.yaml`` (each entry: ``a``, ``b``, ``label``,
optional ``category``), embeds each tool with the same ``fingerprint_text``
the production ingest uses, computes cosine similarity per pair, then
sweeps a configurable list of thresholds and reports precision / recall /
F1 for the **duplicate** class at each.

Usage:
    python3 eval_threshold.py                       # console table
    python3 eval_threshold.py --markdown FILE       # also write a report
    python3 eval_threshold.py --thresholds 0.85,0.88,0.90,0.92,0.95

Cost: one batched embedding call covers the whole pair set (≤ 60 texts at
~3072 dims). Re-run is idempotent — no index writes.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import yaml

# Reuse the same fingerprint + embed code paths as production ingest so the
# evaluation reflects what we actually score in CI.
from embed import embed_texts
from fingerprint import (
    ToolDescriptor,
    fingerprint_text,
    infer_domain_action_entity,
)


# ---------- Fingerprint variants (offline experimentation only) ----------
#
# These are alternative fingerprint shapes evaluated against the same
# labeled set. They DO NOT touch production ingest. The goal is to compare
# separability before deciding whether to change `fingerprint.fingerprint_text`.
#
# Variant authors: keep these pure functions of ToolDescriptor — no I/O, no
# globals — so the per-variant cache key stays stable.

# Naive synonym families. Mapped tokens are replaced in BOTH the action
# inferred from the wire name AND in the description text. Keep small;
# this is a hypothesis test, not an ontology.
_SEARCH_SYNS = {"find", "search", "lookup", "query"}
_CREATE_SYNS = {"create", "new", "add", "insert"}
_GET_SYNS = {"get", "fetch", "read", "retrieve"}
_UPDATE_SYNS = {"update", "modify", "edit", "patch"}
_DELETE_SYNS = {"delete", "remove", "void"}

_SYNONYM_GROUPS = [
    (_SEARCH_SYNS, "search"),
    (_CREATE_SYNS, "create"),
    (_GET_SYNS, "get"),
    (_UPDATE_SYNS, "update"),
    (_DELETE_SYNS, "delete"),
]


def _normalize_verb(token: str) -> str:
    t = token.lower()
    for group, canonical in _SYNONYM_GROUPS:
        if t in group:
            return canonical
    return t


def _normalize_description(text: str) -> str:
    out = []
    for word in text.split():
        # Strip leading/trailing punctuation, normalize, restore.
        head = ""
        tail = ""
        body = word
        while body and not body[0].isalnum():
            head += body[0]
            body = body[1:]
        while body and not body[-1].isalnum():
            tail = body[-1] + tail
            body = body[:-1]
        out.append(head + _normalize_verb(body) + tail if body else word)
    return " ".join(out)


def _fp_baseline(d: ToolDescriptor) -> str:
    """Production fingerprint shape — the control."""
    return fingerprint_text(d)


def _fp_no_domain(d: ToolDescriptor) -> str:
    """Drop the `domain:` line. Hypothesis: the shared `domain: finance`
    token across all governed-mcp tools inflates novel scores."""
    _, action, entity = infer_domain_action_entity(d.name)
    params = d.required_params()
    parts = []
    if action:
        parts.append(f"action: {action}")
    if entity:
        parts.append(f"entity: {entity}")
    if d.description:
        parts.append(f"description: {d.description.strip()}")
    if params:
        parts.append("params: " + ", ".join(sorted(params)))
    return "\n".join(parts)


def _fp_synonyms(d: ToolDescriptor) -> str:
    """Normalize verbs in action + description. Hypothesis: collapsing
    find/search/lookup → search pulls semantic dups closer together."""
    domain, action, entity = infer_domain_action_entity(d.name)
    params = d.required_params()
    parts = []
    if domain:
        parts.append(f"domain: {domain}")
    if action:
        parts.append(f"action: {_normalize_verb(action)}")
    if entity:
        parts.append(f"entity: {entity}")
    if d.description:
        parts.append(f"description: {_normalize_description(d.description.strip())}")
    if params:
        parts.append("params: " + ", ".join(sorted(params)))
    return "\n".join(parts)


def _fp_description_heavy(d: ToolDescriptor) -> str:
    """Repeat the description twice. Hypothesis: weighting the semantic
    payload over the structural tokens improves separability."""
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
        desc = d.description.strip()
        parts.append(f"description: {desc}")
        parts.append(f"intent: {desc}")
    if params:
        parts.append("params: " + ", ".join(sorted(params)))
    return "\n".join(parts)


def _fp_combined(d: ToolDescriptor) -> str:
    """no-domain + synonyms + description-heavy stacked together."""
    _, action, entity = infer_domain_action_entity(d.name)
    params = d.required_params()
    parts = []
    if action:
        parts.append(f"action: {_normalize_verb(action)}")
    if entity:
        parts.append(f"entity: {entity}")
    if d.description:
        desc = _normalize_description(d.description.strip())
        parts.append(f"description: {desc}")
        parts.append(f"intent: {desc}")
    if params:
        parts.append("params: " + ", ".join(sorted(params)))
    return "\n".join(parts)


VARIANTS = {
    "baseline": _fp_baseline,
    "no-domain": _fp_no_domain,
    "synonyms": _fp_synonyms,
    "description-heavy": _fp_description_heavy,
    "combined": _fp_combined,
}


DEFAULT_PAIRS = Path(__file__).parent / "tests" / "labeled_pairs.yaml"
DEFAULT_THRESHOLDS = (0.85, 0.88, 0.90, 0.92, 0.95)


def _to_descriptor(d: dict) -> ToolDescriptor:
    required = d.get("required") or []
    schema = {"required": list(required)} if required else {}
    return ToolDescriptor(
        server=d["server"],
        name=d["name"],
        description=d.get("description", ""),
        input_schema=schema,
    )


def _cosine(u: list[float], v: list[float]) -> float:
    dot = sum(a * b for a, b in zip(u, v))
    nu = math.sqrt(sum(a * a for a in u))
    nv = math.sqrt(sum(b * b for b in v))
    if nu == 0 or nv == 0:
        return 0.0
    return dot / (nu * nv)


def _confusion(pairs: list[dict], threshold: float) -> dict:
    """Count TP/FP/TN/FN for the 'duplicate' positive class."""
    tp = fp = tn = fn = 0
    for p in pairs:
        actual_dup = p["label"] == "duplicate"
        predicted_dup = p["score"] >= threshold
        if actual_dup and predicted_dup:
            tp += 1
        elif actual_dup and not predicted_dup:
            fn += 1
        elif not actual_dup and predicted_dup:
            fp += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _metrics(c: dict) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    if precision + recall and not (math.isnan(precision) or math.isnan(recall)):
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = float("nan")
    return {"precision": precision, "recall": recall, "f1": f1}


def _fmt(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x:.3f}"


def evaluate(pairs_path: Path, thresholds: Iterable[float],
             variant: str = "baseline") -> dict:
    if variant not in VARIANTS:
        raise SystemExit(
            f"unknown variant: {variant!r} (choose from {sorted(VARIANTS)})"
        )
    fp_fn = VARIANTS[variant]

    raw = yaml.safe_load(pairs_path.read_text())
    pairs: list[dict] = raw.get("pairs", [])
    if not pairs:
        raise SystemExit(f"no pairs in {pairs_path}")

    # Build descriptors and dedupe fingerprints so we embed each unique
    # text once. This matters less for small sets but matters a lot if
    # someone grows the file.
    fingerprints: dict[str, int] = {}
    fp_order: list[str] = []
    for pair in pairs:
        for side in ("a", "b"):
            d = _to_descriptor(pair[side])
            text = fp_fn(d)
            pair[f"{side}_fp"] = text
            if text not in fingerprints:
                fingerprints[text] = len(fp_order)
                fp_order.append(text)

    print(
        f"[variant={variant}] embedding {len(fp_order)} unique "
        f"fingerprints for {len(pairs)} pairs...",
        file=sys.stderr,
    )
    vectors = embed_texts(fp_order)

    for pair in pairs:
        ua = vectors[fingerprints[pair["a_fp"]]]
        ub = vectors[fingerprints[pair["b_fp"]]]
        pair["score"] = _cosine(ua, ub)

    # Per-threshold global metrics
    sweep = []
    for t in thresholds:
        c = _confusion(pairs, t)
        m = _metrics(c)
        sweep.append({"threshold": t, **c, **m})

    # Per-category breakdown at the production threshold (0.92)
    by_cat = defaultdict(list)
    for pair in pairs:
        by_cat[pair.get("category", "uncategorized")].append(pair)

    return {"variant": variant, "pairs": pairs, "sweep": sweep,
            "by_category": dict(by_cat)}


def _separability(pairs: list[dict]) -> dict:
    dup_scores = [p["score"] for p in pairs if p["label"] == "duplicate"]
    novel_scores = [p["score"] for p in pairs if p["label"] == "novel"]
    if not dup_scores or not novel_scores:
        return {"min_dup": float("nan"), "max_novel": float("nan"),
                "margin": float("nan")}
    return {
        "min_dup": min(dup_scores),
        "max_novel": max(novel_scores),
        "margin": min(dup_scores) - max(novel_scores),
    }


def evaluate_all_variants(pairs_path: Path,
                          thresholds: Iterable[float]) -> list[dict]:
    """Run every registered variant over the same labeled set, returning
    one result dict per variant. Used by --compare to surface the
    relative impact of fingerprint-shape changes."""
    return [evaluate(pairs_path, thresholds, variant=v) for v in VARIANTS]


def render_comparison(results: list[dict],
                      thresholds: Iterable[float]) -> None:
    """Console-only summary table comparing all variants at each threshold."""
    thresholds = list(thresholds)
    print()
    print("Variant comparison — F1 (duplicate class) at each threshold")
    header = f"{'variant':<20} | " + " ".join(f"{t:>6.3f}" for t in thresholds) + " | sep_margin"
    print(header)
    print("-" * len(header))
    for r in results:
        sweep = {row["threshold"]: row for row in r["sweep"]}
        f1s = " ".join(_fmt(sweep[t]["f1"]).rjust(6) for t in thresholds)
        sep = _separability(r["pairs"])
        margin = _fmt(sep["margin"])
        print(f"{r['variant']:<20} | {f1s} | {margin:>10}")

    print()
    print("Separability (lowest dup − highest novel; >0 means perfectly separable)")
    for r in results:
        sep = _separability(r["pairs"])
        print(
            f"  {r['variant']:<20} "
            f"min_dup={_fmt(sep['min_dup'])}  "
            f"max_novel={_fmt(sep['max_novel'])}  "
            f"margin={_fmt(sep['margin'])}"
        )


def render_console(result: dict) -> None:
    pairs = result["pairs"]
    sweep = result["sweep"]
    print()
    print(f"Variant: {result.get('variant', 'baseline')}")
    print(f"Pairs: {len(pairs)} "
          f"(duplicates={sum(1 for p in pairs if p['label'] == 'duplicate')}, "
          f"novels={sum(1 for p in pairs if p['label'] == 'novel')})")
    print()
    print(
        f"{'threshold':>10} | {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} | "
        f"{'precision':>10} {'recall':>8} {'F1':>6}"
    )
    print("-" * 64)
    for row in sweep:
        print(
            f"{row['threshold']:>10.3f} | "
            f"{row['tp']:>3} {row['fp']:>3} {row['fn']:>3} {row['tn']:>3} | "
            f"{_fmt(row['precision']):>10} "
            f"{_fmt(row['recall']):>8} "
            f"{_fmt(row['f1']):>6}"
        )

    print("\nPer-pair scores (sorted descending):")
    print(f"  {'score':>6}  {'label':>9}  {'category':<26}  pair")
    for p in sorted(pairs, key=lambda x: -x["score"]):
        cat = p.get("category", "")
        a = f"{p['a']['server']}/{p['a']['name']}"
        b = f"{p['b']['server']}/{p['b']['name']}"
        print(f"  {p['score']:>6.3f}  {p['label']:>9}  {cat:<26}  {a}  vs  {b}")


def render_markdown(result: dict, out_path: Path, thresholds: Iterable[float]) -> None:
    pairs = result["pairs"]
    sweep = result["sweep"]
    n_dup = sum(1 for p in pairs if p["label"] == "duplicate")
    n_novel = sum(1 for p in pairs if p["label"] == "novel")

    lines = [
        "# Precision / recall study — L2 similarity threshold",
        "",
        "Generated by `apps/dup-resolver/eval_threshold.py`. To refresh:",
        "",
        "```bash",
        "cd apps/dup-resolver && source .venv/bin/activate",
        "python3 eval_threshold.py --markdown ../../docs/eval/precision-recall.md",
        "```",
        "",
        "## Inputs",
        "",
        f"- Labeled pair set: `apps/dup-resolver/tests/labeled_pairs.yaml`",
        f"- Pairs: **{len(pairs)}** "
        f"(duplicates: {n_dup}, novels: {n_novel})",
        f"- Thresholds swept: {', '.join(f'{t:.3f}' for t in thresholds)}",
        f"- Embedding model: `text-embedding-3-large` (3072 dims, cosine)",
        f"- Fingerprint shape: same as production ingest "
        f"(domain / action / entity / description / params)",
        "",
        "## Sweep",
        "",
        "Positive class is **duplicate**. Each pair contributes to one cell of",
        "the confusion matrix at each threshold.",
        "",
        "| threshold | TP | FP | FN | TN | precision | recall |  F1   |",
        "|----------:|---:|---:|---:|---:|----------:|-------:|------:|",
    ]
    for row in sweep:
        lines.append(
            f"| {row['threshold']:.3f} | "
            f"{row['tp']} | {row['fp']} | {row['fn']} | {row['tn']} | "
            f"{_fmt(row['precision'])} | {_fmt(row['recall'])} | "
            f"{_fmt(row['f1'])} |"
        )

    lines += [
        "",
        "## Per-pair scores",
        "",
        "Sorted descending. The gap between the lowest-scoring duplicate and the",
        "highest-scoring novel is the **separability margin** — wider is better,",
        "and the production threshold should sit inside that gap.",
        "",
        "| score | label | category | a | b |",
        "|------:|-------|----------|---|---|",
    ]
    for p in sorted(pairs, key=lambda x: -x["score"]):
        cat = p.get("category", "")
        a = f"`{p['a']['server']}/{p['a']['name']}`"
        b = f"`{p['b']['server']}/{p['b']['name']}`"
        lines.append(
            f"| {p['score']:.3f} | {p['label']} | {cat} | {a} | {b} |"
        )

    # Separability summary
    dup_scores = [p["score"] for p in pairs if p["label"] == "duplicate"]
    novel_scores = [p["score"] for p in pairs if p["label"] == "novel"]
    if dup_scores and novel_scores:
        min_dup = min(dup_scores)
        max_novel = max(novel_scores)
        margin = min_dup - max_novel
        lines += [
            "",
            "## Separability",
            "",
            f"- Lowest-scoring duplicate: **{min_dup:.3f}**",
            f"- Highest-scoring novel:    **{max_novel:.3f}**",
            f"- Margin: **{margin:+.3f}** "
            f"({'separable' if margin > 0 else 'overlapping'})",
            "",
            "If the margin is negative, no single threshold can perfectly",
            "separate the two classes on this set — pick the threshold that",
            "best matches the cost asymmetry (false positives block PRs;",
            "false negatives let dups through).",
            "",
        ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out_path}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS,
                    help=f"labeled pair YAML (default: {DEFAULT_PAIRS})")
    ap.add_argument("--thresholds", default=",".join(f"{t}" for t in DEFAULT_THRESHOLDS),
                    help="comma-separated thresholds to sweep")
    ap.add_argument("--markdown", type=Path, default=None,
                    help="optional path to write a markdown report")
    ap.add_argument("--variant", default="baseline",
                    choices=sorted(VARIANTS),
                    help="fingerprint variant to evaluate (default: baseline)")
    ap.add_argument("--compare", action="store_true",
                    help="evaluate ALL variants and print a comparison table "
                         "(ignores --markdown)")
    args = ap.parse_args()

    thresholds = tuple(float(t) for t in args.thresholds.split(",") if t)
    if args.compare:
        results = evaluate_all_variants(args.pairs, thresholds)
        render_comparison(results, thresholds)
        return 0
    result = evaluate(args.pairs, thresholds, variant=args.variant)
    render_console(result)
    if args.markdown:
        render_markdown(result, args.markdown, thresholds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
