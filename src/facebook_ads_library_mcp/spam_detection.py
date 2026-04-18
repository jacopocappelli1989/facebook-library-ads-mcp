"""Heuristic spam / low-quality page detection for the Ads Library.

The Meta Ads Library is polluted by clusters of pages that serve interactive
fiction apps (romance webnovels, billionaire-CEO/werewolf tropes, Korean/Chinese
stories with translated keyword stuffing, etc.). They fire hundreds of near
duplicate ads across random topic keywords so they show up in every keyword
search. This module flags those pages so the MCP can auto-exclude them.

Signals:
  - **Novel vocabulary**: phrases that only appear in webnovel/fiction-app ad copy
    ("chapter 1", "fated mate", "werewolf billionaire", "five months pregnant",
    "foster sister", "sacred threshold", etc.).
  - **Global/app-store targeting + generic ad bodies**: ads with targets like
    `iTunes App Store Countries`, `Worldwide`, or `App Store / Google Play` where
    the creative body is fiction narrative.
  - **High duplicate rate on a page**: a page running many ads where the same
    body text repeats across different ad IDs — classic spam-farm signature.

Each detector returns `(confidence: float, evidence: list[str])` so the caller
can decide where to draw the line.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

NOVEL_PHRASES = [
    "chapter 1", "chapter 2", "chapter one",
    "fated mate", "foster sister", "foster brother",
    "billionaire ceo", "rich ceo", "ceo husband", "ex-husband",
    "werewolf", "alpha king", "alpha werewolf", "luna mate",
    "sacred threshold", "pour oil", "pregnancy revenge",
    "years ago, for the sake of", "for the sake of",
    "five months pregnant", "six months pregnant",
    "reborn as", "i was reborn", "reincarnated as",
    "my fated", "my husband's mistress", "the mistress",
    "stepmother", "wicked stepmother",
    "i swore to myself", "i vowed to",
    "mafia boss", "the mafia", "cold-hearted ceo",
    "read now", "read more", "tap to read", "start reading",
    "download and read", "unlock the full story",
]

GENERIC_AFFILIATE_PHRASES = [
    "swipe up", "check the link in bio", "limited stock available",
    "click to learn more about this amazing",
    "this ad was run by an account or page we later disabled",
]

WORLDWIDE_TARGET_NAMES = {
    "worldwide",
    "itunes app store countries",
    "app store",
    "google play",
    "all countries",
    "european economic area (eea)",  # not spam per se, but a flag when paired with others
}


def _lowered_bodies(ads: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for a in ads:
        bodies = a.get("ad_creative_bodies") or []
        for b in bodies:
            if b:
                out.append(str(b).lower())
    return out


def novel_vocab_score(ads: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Fraction of ad bodies containing at least one novel-vocabulary phrase."""
    bodies = _lowered_bodies(ads)
    if not bodies:
        return 0.0, []
    hits: list[str] = []
    matching = 0
    for body in bodies:
        local = [p for p in NOVEL_PHRASES if p in body]
        if local:
            matching += 1
            hits.extend(local[:2])
    return matching / len(bodies), list(dict.fromkeys(hits))[:10]


def worldwide_targeting_score(ads: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Fraction of ads targeting Worldwide / app-store-wide audiences."""
    if not ads:
        return 0.0, []
    matching = 0
    evidence: list[str] = []
    for a in ads:
        locs = a.get("target_locations") or []
        names = [str(t.get("name", "")).lower() for t in locs]
        if any(n in WORLDWIDE_TARGET_NAMES for n in names):
            matching += 1
            evidence.extend(n for n in names if n in WORLDWIDE_TARGET_NAMES)
    return matching / len(ads), list(dict.fromkeys(evidence))[:5]


def duplicate_body_ratio(ads: list[dict[str, Any]]) -> tuple[float, list[str]]:
    """Fraction of ad bodies that are NOT unique (identical body on multiple ad IDs)."""
    bodies = _lowered_bodies(ads)
    if len(bodies) < 3:
        return 0.0, []
    counter = Counter(bodies)
    duplicates = sum(count for _, count in counter.items() if count > 1)
    # evidence: most duplicated body text (trimmed)
    evidence: list[str] = []
    for body, count in counter.most_common(3):
        if count > 1:
            evidence.append(f"x{count}: {body[:80]}")
    return duplicates / len(bodies), evidence


def classify_page(ads_from_page: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify a page (collection of its ads) for spam likelihood.

    Returns a dict with per-signal scores and a combined `is_spam` bool
    along with a reason code. Thresholds are tuned conservatively to minimise
    false positives on legitimate DTC brands.
    """
    if not ads_from_page:
        return {"is_spam": False, "reason": None, "signals": {}}

    novel_score, novel_hits = novel_vocab_score(ads_from_page)
    ww_score, ww_hits = worldwide_targeting_score(ads_from_page)
    dup_score, dup_hits = duplicate_body_ratio(ads_from_page)
    total_ads = len(ads_from_page)

    signals = {
        "ads_sampled": total_ads,
        "novel_vocab_ratio": round(novel_score, 3),
        "novel_vocab_hits": novel_hits,
        "worldwide_target_ratio": round(ww_score, 3),
        "worldwide_target_hits": ww_hits,
        "duplicate_body_ratio": round(dup_score, 3),
        "duplicate_body_examples": dup_hits,
    }

    reason: str | None = None
    # 1. Clear novel-spam: vocabulary signal dominates
    if novel_score >= 0.3 and total_ads >= 3:
        reason = "auto_novel_spam"
    # 2. Worldwide-targeted repetitive content: ad-arbitrage/affiliate pattern
    elif ww_score >= 0.7 and dup_score >= 0.5 and total_ads >= 5:
        reason = "auto_worldwide_duplicate_farm"
    # 3. Very high duplicate rate even without worldwide targeting
    elif dup_score >= 0.75 and total_ads >= 10:
        reason = "auto_duplicate_farm"

    return {
        "is_spam": reason is not None,
        "reason": reason,
        "signals": signals,
    }


def classify_grouped_ads(ads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group ads by page_id, classify each page, return
    `{page_id: {"page_name": str, **classification}}` for pages flagged as spam."""
    by_page: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    for a in ads:
        pid = str(a.get("page_id") or "")
        if not pid:
            continue
        by_page.setdefault(pid, []).append(a)
        if not names.get(pid) and a.get("page_name"):
            names[pid] = str(a["page_name"])

    out: dict[str, dict[str, Any]] = {}
    for pid, page_ads in by_page.items():
        cls = classify_page(page_ads)
        if cls["is_spam"]:
            out[pid] = {"page_name": names.get(pid, ""), **cls}
    return out


def auto_block_recommendation(
    ads_from_page: list[dict[str, Any]],
) -> tuple[bool, str | None, dict[str, Any]]:
    """Stricter version of `classify_page` for auto-blocking on save.

    Run after every ad batch is written to the cache. Uses higher thresholds
    than the manual scan so false positives on legitimate DTC brands are
    minimised — the manual `scan_cache_for_spam` tool remains available with
    looser limits for aggressive cleanups.

    Requires ≥5 ads sampled before it considers blocking at all.
    """
    if len(ads_from_page) < 5:
        return False, None, {"ads_sampled": len(ads_from_page), "skipped": "too_few_ads"}

    novel_score, novel_hits = novel_vocab_score(ads_from_page)
    ww_score, ww_hits = worldwide_targeting_score(ads_from_page)
    dup_score, dup_hits = duplicate_body_ratio(ads_from_page)
    signals = {
        "ads_sampled": len(ads_from_page),
        "novel_vocab_ratio": round(novel_score, 3),
        "novel_vocab_hits": novel_hits,
        "worldwide_target_ratio": round(ww_score, 3),
        "worldwide_target_hits": ww_hits,
        "duplicate_body_ratio": round(dup_score, 3),
        "duplicate_body_examples": dup_hits,
    }

    # High-confidence conditions only — stricter than manual scan.
    if novel_score >= 0.4:
        return True, "auto_novel_spam", signals
    if ww_score >= 0.9 and dup_score >= 0.7:
        return True, "auto_worldwide_duplicate_farm", signals
    if dup_score >= 0.85 and len(ads_from_page) >= 15:
        return True, "auto_duplicate_farm", signals
    return False, None, signals
