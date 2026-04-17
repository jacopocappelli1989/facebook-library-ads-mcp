"""Side-by-side competitive comparison across multiple page IDs."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .. import cache
from ..client import graph_get
from ..constants import LIGHT_FIELDS


async def _fetch_page_ads(
    page_id: str,
    ad_reached_countries: list[str],
    ad_active_status: str,
    limit: int,
) -> dict[str, Any]:
    params = {
        "ad_reached_countries": ",".join(ad_reached_countries),
        "search_page_ids": page_id,
        "ad_active_status": ad_active_status,
        "ad_type": "ALL",
        "limit": limit,
        "fields": ",".join(LIGHT_FIELDS),
    }
    resp = await graph_get("/ads_archive", params)
    cache.save_ads(resp.get("data") or [])
    return resp


def _summarize(ads: list[dict[str, Any]]) -> dict[str, Any]:
    platforms: Counter[str] = Counter()
    active = 0
    inactive = 0
    page_name = None
    for ad in ads:
        page_name = page_name or ad.get("page_name")
        if ad.get("ad_delivery_stop_time"):
            inactive += 1
        else:
            active += 1
        for p in ad.get("publisher_platforms", []) or []:
            platforms[p] += 1
    return {
        "page_name": page_name,
        "ads_in_sample": len(ads),
        "active_in_sample": active,
        "inactive_in_sample": inactive,
        "platform_distribution": dict(platforms.most_common()),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def compare_brands(
        page_ids: list[str],
        ad_reached_countries: list[str],
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ALL",
        per_brand_limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch ads for each page ID in parallel and return a summary per brand.

        Summary includes ads_in_sample, active/inactive counts, and
        platform distribution. Ideal for head-to-head competitor snapshots.
        """
        if not page_ids:
            raise ValueError("page_ids must not be empty")
        if len(page_ids) > 20:
            raise ValueError("compare up to 20 pages per call")

        results = await asyncio.gather(
            *(
                _fetch_page_ads(pid, ad_reached_countries, ad_active_status, per_brand_limit)
                for pid in page_ids
            ),
            return_exceptions=True,
        )
        summaries: dict[str, Any] = {}
        for pid, res in zip(page_ids, results):
            if isinstance(res, Exception):
                summaries[pid] = {"error": str(res)}
                continue
            summaries[pid] = _summarize(res.get("data", []))
        return {
            "ad_reached_countries": ad_reached_countries,
            "ad_active_status": ad_active_status,
            "per_brand_limit": per_brand_limit,
            "brands": summaries,
        }
