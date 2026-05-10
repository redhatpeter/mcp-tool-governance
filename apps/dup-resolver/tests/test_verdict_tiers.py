"""Verdict-tier regression test for check_pr._verdict_at.

The two-tier verdict model added 2026-05-10 (per docs/eval/precision-recall.md):

    score >= threshold              → DUPLICATE  (hard block, fails CI)
    score >= threshold - 0.05       → WARN       (close to threshold)
    score >= REVIEW_THRESHOLD       → REVIEW     (soft, surfaced in PR comment)
    otherwise                       → OK

Run from apps/dup-resolver/ (so config + check_pr import cleanly).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import check_pr  # noqa: E402


def _expect(score: float, threshold: float, want: str) -> None:
    got = check_pr._verdict_at(score, threshold)
    assert got == want, (
        f"score={score} threshold={threshold} review={config.REVIEW_THRESHOLD} "
        f"→ got {got!r}, want {want!r}"
    )


def test_verdict_tiers_at_default_threshold() -> None:
    t = 0.92  # representative production threshold
    # DUPLICATE band
    _expect(1.000, t, "DUPLICATE")
    _expect(0.920, t, "DUPLICATE")
    # WARN band [t-0.05, t)
    _expect(0.910, t, "WARN")
    _expect(0.870, t, "WARN")
    # REVIEW band [REVIEW_THRESHOLD, t-0.05)
    _expect(0.800, t, "REVIEW")
    _expect(config.REVIEW_THRESHOLD, t, "REVIEW")
    # OK band
    just_below = max(0.0, config.REVIEW_THRESHOLD - 0.001)
    _expect(just_below, t, "OK")
    _expect(0.0, t, "OK")


def test_review_tier_catches_real_world_cross_vendor_duplicates() -> None:
    """Pairs sourced from docs/eval/precision-recall.md that single-tier missed.

    All of these should land in REVIEW (not OK) so reviewers see them in
    the PR comment, but should NOT be DUPLICATE (precision protected).
    """
    t = 0.92
    real_world_cross_vendor = {
        "github.create_issue vs linear.createIssue": 0.651,
        "slack.post_message vs discord.send_message": 0.665,
        "fetch.fetch vs puppeteer.navigate": 0.546,  # below 0.65 → OK is fine
        "filesystem.read_file vs gdrive.read_file": 0.654,
        "postgres.query vs sqlite.read_query": 0.695,
        "brave_web_search vs google_web_search": 0.782,
    }
    for label, score in real_world_cross_vendor.items():
        v = check_pr._verdict_at(score, t)
        if score >= config.REVIEW_THRESHOLD:
            assert v == "REVIEW", f"{label} (score={score}) → {v}, want REVIEW"
        else:
            assert v == "OK", f"{label} (score={score}) → {v}, want OK"


def test_review_threshold_default() -> None:
    # Sanity: default lines up with the recommendation in
    # docs/eval/precision-recall.md.
    assert config.REVIEW_THRESHOLD == 0.65, (
        f"REVIEW_THRESHOLD default changed: {config.REVIEW_THRESHOLD}"
    )


if __name__ == "__main__":
    test_verdict_tiers_at_default_threshold()
    test_review_tier_catches_real_world_cross_vendor_duplicates()
    test_review_threshold_default()
    print("ok: 3 verdict-tier tests")
