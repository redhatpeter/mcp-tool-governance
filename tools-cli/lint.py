"""
tools-cli lint — design-time gate for the MCP Tool Governance PoC (Layer 1).

Validates OpenAPI specs that will be exposed as APIM-MCP servers, enforcing the
naming standard (§9) on the **operation `summary`** field, because that is
what APIM-MCP normalizes into the wire tool name the LLM actually sees.
(See ARCHITECTURE.md §3.2 — authored vs wire name.)

Usage:
    python tools-cli/lint.py [--json] [SPEC ...]

If no SPEC paths are given, lints every *.json under apim/openapi/.

Exit codes:
    0  no errors (warnings ok)
    1  one or more errors (use in CI to block merges)
    2  invalid invocation (file not found, bad JSON, etc.)

Rules (E* = error, W* = warning):

  E001  Operation has no `summary`.
  E002  Wire name (camelCased summary) violates ^[a-z][a-zA-Z0-9]{2,63}$.
  E003  Two operations in the same spec produce the same wire name (collision —
        APIM-MCP silently drops one). This is failure mode #5.
  E004  Wire name lacks an approved domain prefix.
  E005  Action token (last camelCase token) is not in the approved verb list.
  E006  Summary contains a banned legacy/version marker (v1, v2, final, legacy,
        new, old).
  W101  Description missing or shorter than 40 chars (rich descriptions
        materially improve LLM tool-pick correctness — see eval results).
  W102  Description does not contain "USE WHEN" or "DO NOT USE" guidance.

Tunable via environment:
  LINT_DOMAINS      comma-separated allowed domain prefixes
                    (default: finance,customer,hr,sales,operations)
  LINT_VERBS        comma-separated allowed action verbs
                    (default: get,list,search,create,update,delete,
                              summarize,validate,approve,reject,void)
  LINT_MIN_DESC     minimum description length for W101 (default: 40)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = "apim/openapi/*.json"

DOMAINS = [d.strip() for d in os.environ.get(
    "LINT_DOMAINS", "finance,customer,hr,sales,operations"
).split(",") if d.strip()]
VERBS = [v.strip() for v in os.environ.get(
    "LINT_VERBS",
    "get,list,search,create,update,delete,summarize,validate,approve,reject,void"
).split(",") if v.strip()]
MIN_DESC = int(os.environ.get("LINT_MIN_DESC", "40"))

BANNED_MARKERS = re.compile(r"(?:^|[^a-z0-9])(v\d+|final|legacy|new|old)(?:[^a-z0-9]|$)", re.I)
WIRE_NAME_RE = re.compile(r"^[a-z][a-zA-Z0-9]{2,63}$")
SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


@dataclass
class Finding:
    severity: str   # "E" or "W"
    code: str       # e.g. "E003"
    spec: str
    op_path: str    # "GET /governed/customers"
    summary: str
    wire_name: str
    message: str

    def fmt(self) -> str:
        sev = "ERROR  " if self.severity == "E" else "warn   "
        return (f"  {sev} {self.code}  {self.op_path:42}"
                f"  summary={self.summary!r:36}  -> wire={self.wire_name!r}\n"
                f"           {self.message}")

    def to_dict(self) -> dict:
        return {
            "severity": self.severity, "code": self.code, "spec": self.spec,
            "op_path": self.op_path, "summary": self.summary,
            "wire_name": self.wire_name, "message": self.message,
        }


@dataclass
class Operation:
    spec: str
    op_path: str         # "GET /governed/customers"
    summary: str
    description: str


def camel_case_wire_name(summary: str) -> str:
    """Mirror APIM-MCP's normalization rule (verified against apimopenai99
    governed-mcp + messy-mcp tools/list, 2026-05-08):

      1. Split the summary on any non-identifier character (_, -, space, .).
      2. For each token, uppercase only the FIRST character, preserve the rest.
      3. Concatenate.
      4. Lowercase only the first character of the result.

    This matches the empirical behavior including the collision we observed
    where `createCustomer` and `Create_Customer` both surface as wire name
    `createCustomer` (APIM-MCP silently drops one).
    """
    if not summary:
        return ""
    tokens = [t for t in SPLIT_RE.split(summary) if t]
    if not tokens:
        return ""
    pascal = "".join(t[:1].upper() + t[1:] for t in tokens)
    return pascal[:1].lower() + pascal[1:]


def iter_operations(spec_path: Path) -> Iterable[Operation]:
    raw = json.loads(spec_path.read_text())
    for url, methods in (raw.get("paths") or {}).items():
        for method, op in (methods or {}).items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            if not isinstance(op, dict):
                continue
            yield Operation(
                spec=spec_path.name,
                op_path=f"{method.upper()} {url}",
                summary=str(op.get("summary") or ""),
                description=str(op.get("description") or ""),
            )


def lint_spec(spec_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    seen_wire: dict[str, str] = {}     # wire_name -> first op_path that produced it

    try:
        ops = list(iter_operations(spec_path))
    except json.JSONDecodeError as e:
        return [Finding("E", "E000", spec_path.name, "<file>", "", "",
                        f"invalid JSON: {e}")]

    for op in ops:
        wire = camel_case_wire_name(op.summary)

        # E001: missing summary
        if not op.summary.strip():
            findings.append(Finding("E", "E001", op.spec, op.op_path, op.summary, wire,
                                    "operation is missing `summary` — APIM-MCP "
                                    "won't have a wire name to expose"))
            continue   # later checks need a wire name

        # E002: bad wire name shape
        if not WIRE_NAME_RE.match(wire):
            findings.append(Finding("E", "E002", op.spec, op.op_path, op.summary, wire,
                                    f"normalized wire name {wire!r} fails "
                                    "^[a-z][a-zA-Z0-9]{2,63}$"))

        # E003: wire-name collision
        if wire in seen_wire:
            findings.append(Finding("E", "E003", op.spec, op.op_path, op.summary, wire,
                                    f"collision: {seen_wire[wire]} already produces "
                                    f"wire name {wire!r}; APIM-MCP will silently drop one"))
        else:
            seen_wire[wire] = op.op_path

        # E004: domain prefix
        if not any(wire.startswith(d) for d in DOMAINS):
            findings.append(Finding("E", "E004", op.spec, op.op_path, op.summary, wire,
                                    f"wire name does not start with an approved domain "
                                    f"({', '.join(DOMAINS)})"))

        # E005: action verb
        # Last token = trailing run of capitalized letters interpreted as a token.
        tokens = [t for t in SPLIT_RE.split(op.summary) if t]
        last = tokens[-1].lower() if tokens else ""
        if last and last not in VERBS:
            findings.append(Finding("E", "E005", op.spec, op.op_path, op.summary, wire,
                                    f"action token {last!r} is not in the approved "
                                    f"verb list ({', '.join(VERBS)})"))

        # E006: banned markers
        if BANNED_MARKERS.search(op.summary):
            findings.append(Finding("E", "E006", op.spec, op.op_path, op.summary, wire,
                                    "summary contains a banned version/legacy marker "
                                    "(v1, v2, final, legacy, new, old) — encode versions "
                                    "in the OpenAPI `info.version` field instead"))

        # W101: thin description
        desc = op.description.strip()
        if len(desc) < MIN_DESC:
            findings.append(Finding("W", "W101", op.spec, op.op_path, op.summary, wire,
                                    f"description is {len(desc)} chars (min {MIN_DESC}); "
                                    "rich descriptions improve tool-pick correctness"))

        # W102: missing USE WHEN / DO NOT USE
        elif "use when" not in desc.lower() and "do not use" not in desc.lower():
            findings.append(Finding("W", "W102", op.spec, op.op_path, op.summary, wire,
                                    "description lacks 'USE WHEN' / 'DO NOT USE' "
                                    "disambiguation guidance"))

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", nargs="*", help="OpenAPI .json files to lint "
                    f"(default: {DEFAULT_GLOB})")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of human output")
    ap.add_argument("--no-warn", action="store_true",
                    help="suppress warnings; only errors")
    args = ap.parse_args()

    if args.specs:
        specs = [Path(p) for p in args.specs]
    else:
        specs = sorted(REPO_ROOT.glob(DEFAULT_GLOB))

    if not specs:
        print(f"no OpenAPI specs found (looked in {REPO_ROOT/DEFAULT_GLOB})",
              file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    for s in specs:
        if not s.exists():
            print(f"not found: {s}", file=sys.stderr)
            return 2
        all_findings.extend(lint_spec(s))

    if args.no_warn:
        all_findings = [f for f in all_findings if f.severity == "E"]

    if args.json:
        print(json.dumps([f.to_dict() for f in all_findings], indent=2))
    else:
        by_spec: dict[str, list[Finding]] = {}
        for f in all_findings:
            by_spec.setdefault(f.spec, []).append(f)
        for spec in sorted({s.name for s in specs}):
            ops_in_spec = sum(1 for _ in iter_operations(next(s for s in specs if s.name == spec)))
            findings = by_spec.get(spec, [])
            errs = sum(1 for f in findings if f.severity == "E")
            warns = sum(1 for f in findings if f.severity == "W")
            status = "FAIL" if errs else ("warn" if warns else "ok")
            print(f"\n[{status}] {spec}  ({ops_in_spec} ops, {errs} errors, {warns} warnings)")
            for f in findings:
                print(f.fmt())
        total_e = sum(1 for f in all_findings if f.severity == "E")
        total_w = sum(1 for f in all_findings if f.severity == "W")
        print(f"\n=== TOTAL: {total_e} errors, {total_w} warnings across {len(specs)} spec(s) ===")

    return 1 if any(f.severity == "E" for f in all_findings) else 0


if __name__ == "__main__":
    sys.exit(main())
