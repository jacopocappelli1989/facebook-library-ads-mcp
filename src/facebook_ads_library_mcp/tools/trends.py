"""Google Trends lookup for seasonality / growth signals.

Hits the public (undocumented) Trends endpoints directly via httpx — no
pytrends/pandas/numpy dependency, fewer moving parts.

Flow:
1. `GET /trends/hottrends/` → seed cookies (the `NID` cookie is required for
   subsequent requests to work).
2. `GET /trends/api/explore` with the payload → returns a list of widgets
   including an `interest over time` widget whose token we need.
3. `GET /trends/api/widgetdata/multiline` with that token → returns the
   timeseries. Both endpoints prefix JSON responses with `)]}',\\n` which we
   strip before parsing.

Google can rate-limit or temporarily block. The tool surfaces a clear error
field when that happens rather than raising.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from .. import cache as _cache

_TRENDS_BASE = "https://trends.google.com/trends"
_EXPLORE_URL = f"{_TRENDS_BASE}/api/explore"
_MULTILINE_URL = f"{_TRENDS_BASE}/api/widgetdata/multiline"
_HOT_URL = f"{_TRENDS_BASE}/hottrends/"

def _strip_prefix(text: str) -> str:
    """Strip the anti-XSSI prefix Google prepends to JSON responses.

    Known variants across the Trends endpoints:
      `)]}'`    (explore)
      `)]}',`   (widgetdata/multiline)
    """
    s = text.lstrip()
    if s.startswith(")]}'"):
        s = s[4:]
    if s.startswith(","):
        s = s[1:]
    return s.strip()


def _slope_pct(values: list[float]) -> float | None:
    n = len(values)
    if n < 4:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0 or mean_y == 0:
        return None
    slope = num / den
    total_change = slope * (n - 1)
    return round((total_change / mean_y) * 100, 2)


def _peak_months(records: list[dict[str, Any]], kw: str) -> list[int]:
    if not records:
        return []
    month_totals: dict[int, list[float]] = {}
    for r in records:
        val = r.get(kw)
        if val is None:
            continue
        month = int(r["date"].split("-")[1])
        month_totals.setdefault(month, []).append(float(val))
    avgs = {m: sum(v) / len(v) for m, v in month_totals.items() if v}
    if not avgs:
        return []
    max_avg = max(avgs.values())
    return sorted([m for m, a in avgs.items() if a >= max_avg * 0.9])


async def _fetch_trends(
    keywords: list[str], timeframe: str, geo: str, hl: str, category: int
) -> dict[str, Any]:
    payload = {
        "comparisonItem": [
            {"keyword": kw, "geo": geo, "time": timeframe} for kw in keywords
        ],
        "category": category,
        "property": "",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": hl,
        "Referer": _TRENDS_BASE + "/",
    }

    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=30.0
    ) as client:
        # Seed cookies. Google sometimes sets NID here; missing NID → 429 later.
        try:
            await client.get(_HOT_URL)
        except httpx.HTTPError:
            pass

        try:
            explore = await client.get(
                _EXPLORE_URL,
                params={
                    "hl": hl,
                    "tz": "0",
                    "req": json.dumps(payload, separators=(",", ":")),
                },
            )
        except httpx.HTTPError as exc:
            return {"error": f"explore request failed: {type(exc).__name__}: {exc}"}

        if explore.status_code != 200:
            return {
                "error": f"explore returned HTTP {explore.status_code}",
                "body_preview": explore.text[:200],
            }

        try:
            widgets = json.loads(_strip_prefix(explore.text)).get("widgets", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            return {"error": f"explore parse failed: {exc}"}

        widget = next((w for w in widgets if w.get("id") == "TIMESERIES"), None)
        if not widget:
            return {"error": "no TIMESERIES widget returned by Google Trends"}

        token = widget.get("token")
        req = widget.get("request")
        if not token or req is None:
            return {"error": "widget missing token/request"}

        # Trends often 429s when multiline is called immediately after explore.
        # Small jittered delay + a couple of retries is enough in practice.
        data: dict[str, Any] | None = None
        last_error: str | None = None
        for attempt in range(3):
            await asyncio.sleep(0.6 + attempt * 0.8 + random.uniform(0, 0.3))
            try:
                multiline = await client.get(
                    _MULTILINE_URL,
                    params={
                        "hl": hl,
                        "tz": "0",
                        "req": json.dumps(req, separators=(",", ":")),
                        "token": token,
                    },
                )
            except httpx.HTTPError as exc:
                last_error = f"multiline request failed: {type(exc).__name__}: {exc}"
                continue

            if multiline.status_code == 429:
                last_error = "multiline returned HTTP 429 (Google Trends rate limit)"
                continue
            if multiline.status_code != 200:
                return {
                    "error": f"multiline returned HTTP {multiline.status_code}",
                    "body_preview": multiline.text[:200],
                }
            try:
                data = json.loads(_strip_prefix(multiline.text))
                break
            except json.JSONDecodeError as exc:
                last_error = f"multiline parse failed: {exc}"
                continue

        if data is None:
            return {"error": last_error or "multiline failed after retries"}

    timeline = data.get("default", {}).get("timelineData") or []
    records: list[dict[str, Any]] = []
    for point in timeline:
        try:
            date = datetime.fromtimestamp(int(point["time"])).strftime("%Y-%m-%d")
        except (KeyError, TypeError, ValueError):
            continue
        rec: dict[str, Any] = {"date": date}
        for idx, value in enumerate(point.get("value") or []):
            if idx < len(keywords):
                rec[keywords[idx]] = int(value) if value is not None else None
        records.append(rec)

    summary: dict[str, Any] = {}
    for kw in keywords:
        values = [r[kw] for r in records if r.get(kw) is not None]
        summary[kw] = {
            "mean": round(sum(values) / len(values), 2) if values else None,
            "max": max(values) if values else None,
            "min": min(values) if values else None,
            "peak_months": _peak_months(records, kw),
            "growth_pct": _slope_pct([float(v) for v in values]),
        }

    return {
        "keywords": keywords,
        "timeframe": timeframe,
        "geo": geo or "WORLD",
        "records": records,
        "summary": summary,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def google_trends_check(
        keywords: list[str],
        timeframe: str = "today 5-y",
        geo: str = "",
        hl: str = "en-US",
        category: int = 0,
        cache_ttl_seconds: int = 21600,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Google Trends interest-over-time for up to 5 keywords.

        Args:
            keywords: 1–5 search terms (product names, niches, brand names).
            timeframe: Trends syntax, e.g. `"today 12-m"`, `"today 5-y"`,
                `"2023-01-01 2024-12-31"`, `"now 7-d"`. Default: 5 years.
            geo: ISO country code (`"US"`, `"PL"`, `"IT"`) or empty for worldwide.
            hl: UI language.
            category: Trends category ID (0 = all).
            cache_ttl_seconds: how long to reuse a cached response. Default 6h —
                trends data updates slowly and Google rate-limits aggressively,
                so caching is a big win.
            force_refresh: bypass cache and hit Trends again.

        Returns raw `records` (date + interest 0-100 per keyword) plus a
        `summary` per keyword with `mean`, `max`, `min`, `peak_months`
        (1-12), and `growth_pct` (linear-regression slope). Raw numbers, no
        verdict.
        """
        if not keywords:
            raise ValueError("keywords must not be empty")
        if len(keywords) > 5:
            raise ValueError("Google Trends accepts at most 5 keywords per request")

        cache_key = "trends:" + hashlib.sha1(
            json.dumps(
                {"kw": sorted(keywords), "tf": timeframe, "geo": geo, "hl": hl, "cat": category},
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if not force_refresh and cache_ttl_seconds > 0:
            hit = _cache.get_page_stats(cache_key, cache_ttl_seconds)
            if hit is not None:
                hit["_from_cache"] = True
                return hit

        result = await _fetch_trends(keywords, timeframe, geo, hl, category)
        if "error" not in result:
            _cache.save_page_stats(cache_key, result)
        return result
