"""Competitor validation orchestrator.

Combines existing building blocks (`page_stats`, `check_shopify_store`, raw
Graph fetch for launch dates) into a single scorecard. Returns raw numbers —
no pass/fail verdicts; the caller applies task-specific thresholds.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import graph_get
from ..filters import _parse_ts, is_active
from .shopify import inspect_shopify_store


async def _fetch_launch_dates(
    page_id: str, ad_reached_countries: list[str], sample_size: int
) -> dict[str, Any]:
    """Pull a broad sample and compute oldest/newest delivery_start."""
    params = {
        "ad_reached_countries": ",".join(ad_reached_countries),
        "search_page_ids": page_id,
        "ad_active_status": "ALL",
        "ad_type": "ALL",
        "limit": min(100, sample_size),
        "fields": "id,ad_delivery_start_time,ad_delivery_stop_time",
    }
    resp = await graph_get("/ads_archive", params)
    ads = resp.get("data", [])
    starts = [a.get("ad_delivery_start_time") for a in ads if a.get("ad_delivery_start_time")]
    active = sum(1 for a in ads if is_active(a))
    inactive = len(ads) - active
    if not starts:
        return {
            "ads_in_sample": len(ads),
            "active_count": active,
            "inactive_count": inactive,
            "oldest_delivery_start": None,
            "newest_delivery_start": None,
            "days_since_oldest": None,
            "days_since_newest": None,
            "active_pct": None,
            "inactive_pct": None,
        }
    now = datetime.now(timezone.utc)
    oldest = min(starts)
    newest = max(starts)
    oldest_dt = _parse_ts(oldest)
    newest_dt = _parse_ts(newest)
    return {
        "ads_in_sample": len(ads),
        "active_count": active,
        "inactive_count": inactive,
        "active_pct": round(100 * active / len(ads), 1) if ads else None,
        "inactive_pct": round(100 * inactive / len(ads), 1) if ads else None,
        "oldest_delivery_start": oldest,
        "newest_delivery_start": newest,
        "days_since_oldest": (now - oldest_dt).days if oldest_dt else None,
        "days_since_newest": (now - newest_dt).days if newest_dt else None,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def validate_competitor(
        page_id: str,
        ad_reached_countries: list[str],
        domain: str | None = None,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Gather all deterministic competitor signals into one scorecard.

        Runs in parallel:
        1. `/ads_archive` sample to compute `ads_in_sample`, `active_count`,
           `inactive_count`, `active_pct`, oldest/newest delivery start, and
           `days_since_oldest`/`days_since_newest` (proxy for "launched X
           days ago").
        2. `check_shopify_store(domain)` if `domain` is provided: returns
           `is_shopify`, `theme_name` (raw, no pass/fail), and `product_count`.

        Returns raw numbers only. Example usage:
        - "launched 7–60 days ago" → check `days_since_newest <= 60 AND
          days_since_oldest >= 7` (or similar, depending on your framing).
        - "not more than 75% ads off" → `inactive_pct <= 75`.
        - "min 30 active ads" → `active_count >= 30`.
        - "1-product store" → `product_count == 1`.
        - "regular Shopify theme" → `theme_name` against your theme list.
        """
        if sample_size < 1:
            raise ValueError("sample_size must be >= 1")

        ads_task = _fetch_launch_dates(page_id, ad_reached_countries, sample_size)
        if domain:
            ads_data, shopify_data = await asyncio.gather(
                ads_task,
                inspect_shopify_store(domain, include_sample_products=False),
            )
        else:
            ads_data = await ads_task
            shopify_data = None

        return {
            "page_id": page_id,
            "ad_reached_countries": ad_reached_countries,
            "sample_size": sample_size,
            "ads": ads_data,
            "shopify": shopify_data,
        }
