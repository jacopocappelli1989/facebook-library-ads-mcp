"""Discover Page IDs by brand name (the ads_archive doesn't expose a name→id lookup,
so we bootstrap it by searching ads for the brand term and aggregating unique pages)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .. import cache
from ..client import graph_get
from ..constants import LIGHT_FIELDS


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def find_pages_by_name(
        brand_name: str,
        ad_reached_countries: list[str],
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ALL",
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Resolve a brand name to candidate Facebook Page IDs.

        The Ads Library API has no `/pages/search` endpoint for public use, so we
        bootstrap it: query `/ads_archive` with `search_terms=brand_name` and
        aggregate unique `(page_id, page_name)` pairs from the returned ads.

        Returns candidates sorted by ad count (most likely = top). Always verify
        manually before using `page_id` downstream — common brand names will
        produce false positives.
        """
        params = {
            "ad_reached_countries": ",".join(ad_reached_countries),
            "search_terms": brand_name,
            "ad_active_status": ad_active_status,
            "ad_type": "ALL",
            "limit": sample_size,
            "fields": ",".join(LIGHT_FIELDS),
        }
        resp = await graph_get("/ads_archive", params)
        cache.save_ads(resp.get("data") or [])
        counts: Counter[tuple[str, str]] = Counter()
        for ad in resp.get("data", []):
            pid = ad.get("page_id")
            name = ad.get("page_name")
            if pid and name:
                counts[(str(pid), str(name))] += 1
        candidates = [
            {"page_id": pid, "page_name": name, "ad_count_in_sample": n}
            for (pid, name), n in counts.most_common()
        ]
        return {
            "brand_name": brand_name,
            "sample_size": sample_size,
            "ads_seen": len(resp.get("data", [])),
            "candidates": candidates,
        }
