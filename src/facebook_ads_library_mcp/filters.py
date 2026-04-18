"""Client-side predicates for filtering ArchivedAd results.

The Graph Ads Library API exposes only a few server-side filters (country, active
status, ad_type, media_type, publisher_platforms, date range, language, search
terms). Everything else — text length, keyword AND/OR, days-since-launch,
spend bands in EUR, niche classification — must be post-filtered on the client.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


# ---------- text helpers --------------------------------------------------- #

TEXT_FIELDS = (
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_creative_link_captions",
)


def extract_text(ad: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in TEXT_FIELDS:
        val = ad.get(field) or []
        if isinstance(val, list):
            parts.extend(str(x) for x in val if x)
        elif val:
            parts.append(str(val))
    return " \n ".join(parts)


def text_length(ad: dict[str, Any]) -> int:
    return len(extract_text(ad))


def contains_all(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return all(k.lower() in lowered for k in keywords)


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


# ---------- date helpers --------------------------------------------------- #

def _parse_ts(value: str | None) -> datetime | None:
    """Parse a Graph API timestamp to an always-TZ-aware datetime (UTC).

    Graph returns a mix of formats: `"2024-11-03T08:00:00+0000"`,
    `"2024-11-03"` (date-only), and occasionally plain ISO. We coerce the
    result to UTC-aware so arithmetic with `datetime.now(timezone.utc)`
    doesn't raise "can't subtract offset-naive and offset-aware datetimes".
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("+0000", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def days_since(value: str | None, *, now: datetime | None = None) -> int | None:
    ts = _parse_ts(value)
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0, (now - ts).days)


def is_active(ad: dict[str, Any]) -> bool:
    """Heuristic: if `ad_delivery_stop_time` is empty/None, the ad is still running."""
    stop = ad.get("ad_delivery_stop_time")
    return not stop


def days_active(ad: dict[str, Any], *, now: datetime | None = None) -> int | None:
    start = _parse_ts(ad.get("ad_delivery_start_time"))
    if start is None:
        return None
    stop = _parse_ts(ad.get("ad_delivery_stop_time"))
    end = stop or now or datetime.now(timezone.utc)
    return max(0, (end - start).days)


# ---------- spend helpers -------------------------------------------------- #

def spend_bounds(ad: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    """Return (lower, upper, currency) from the InsightsRangeValue `spend` field.

    Only political/issue ads in EU have this populated.
    """
    spend = ad.get("spend") or {}
    if not isinstance(spend, dict):
        return None, None, None
    lo = spend.get("lower_bound")
    hi = spend.get("upper_bound")
    cur = spend.get("currency")
    try:
        lo_f = float(lo) if lo is not None else None
    except (TypeError, ValueError):
        lo_f = None
    try:
        hi_f = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        hi_f = None
    return lo_f, hi_f, cur
