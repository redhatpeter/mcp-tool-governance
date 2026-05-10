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
from fingerprint import ToolDescriptor, fingerprint_text


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


def evaluate(pairs_path: Path, thresholds: Iterable[float]) -> dict:
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
            text = fingerprint_text(d)
            pair[f"{side}_fp"] = text
            if text not in fingerprints:
                fingerprints[text] = len(fp_order)
                fp_order.append(text)

    print(
        f"embedding {len(fp_order)} unique fingerprints "
        f"for {len(pairs)} pairs...",
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

    return {"pairs": pairs, "sweep": sweep, "by_category": dict(by_cat)}


def render_console(result: dict) -> None:
    pairs = result["pairs"]
    sweep = result["sweep"]
    print()
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
    args = ap.parse_args()

    thresholds = tuple(float(t) for t in args.thresholds.split(",") if t)
    result = evaluate(args.pairs, thresholds)
    render_console(result)
    if args.markdown:
        render_markdown(result, args.markdown, thresholds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
