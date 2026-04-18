"""Page moderation: manually block/unblock pages and auto-detect spam in the cache.

The cache stores every ad we've ever seen, including spam. Moderation keeps a
separate `blocked_pages` table: read paths filter against it so the spam is
hidden from search results without being destroyed (you can always unblock).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .. import cache
from ..spam_detection import classify_grouped_ads, classify_page


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def block_page(
        page_id: str,
        page_name: str = "",
        reason: str = "manual",
        evidence: str = "",
    ) -> dict[str, Any]:
        """Add a page_id to the block list. Blocked pages are excluded from all
        search results by default (opt-in via `include_blocked=True`).

        `reason` is free-form — suggested values: `manual`, `auto_novel_spam`,
        `auto_duplicate_farm`, `auto_worldwide_duplicate_farm`, `scam`.
        """
        newly = cache.block_page(
            page_id,
            page_name=page_name,
            reason=reason,
            source="manual" if reason == "manual" else "auto",
            evidence=evidence,
        )
        return {"page_id": page_id, "newly_blocked": newly}

    @mcp.tool()
    def unblock_page(page_id: str) -> dict[str, Any]:
        """Remove a page_id from the block list."""
        deleted = cache.unblock_page(page_id)
        return {"page_id": page_id, "was_blocked": deleted}

    @mcp.tool()
    def list_blocked_pages(limit: int = 500) -> dict[str, Any]:
        """Return all currently blocked pages with metadata (reason, source,
        evidence, when added)."""
        rows = cache.list_blocked_pages(limit=limit)
        return {"count": len(rows), "data": rows}

    @mcp.tool()
    def scan_cache_for_spam(
        min_ads_per_page: int = 3,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Scan every page present in the local cache and flag those matching
        spam heuristics (novel vocabulary, worldwide-target duplicate farms,
        high duplicate body ratio).

        Args:
            min_ads_per_page: skip pages with fewer ads than this — too little
                data to classify confidently.
            dry_run: if True, returns what WOULD be blocked without touching
                the block list. If False, auto-blocks them.

        Returns a report with per-page signals so you can audit decisions.
        """
        # Load ads INCLUDING already-blocked pages, since re-scanning them is
        # harmless (insert is idempotent) and may update evidence.
        all_ads = cache.load_ads(limit=100000, exclude_blocked=False)
        grouped = classify_grouped_ads(all_ads)
        newly_blocked: list[dict[str, Any]] = []
        already_blocked: list[str] = []
        skipped_small: list[str] = []

        for page_id, cls in grouped.items():
            if cls["signals"]["ads_sampled"] < min_ads_per_page:
                skipped_small.append(page_id)
                continue
            if cache.is_blocked(page_id):
                already_blocked.append(page_id)
                continue
            entry = {
                "page_id": page_id,
                "page_name": cls["page_name"],
                "reason": cls["reason"],
                "signals": cls["signals"],
            }
            if not dry_run:
                cache.block_page(
                    page_id,
                    page_name=cls["page_name"],
                    reason=cls["reason"] or "auto_spam",
                    source="auto_scan",
                    evidence=json.dumps(cls["signals"], ensure_ascii=False),
                )
            newly_blocked.append(entry)

        return {
            "dry_run": dry_run,
            "ads_scanned": len(all_ads),
            "pages_flagged": len(newly_blocked),
            "already_blocked_skipped": len(already_blocked),
            "too_few_ads_skipped": len(skipped_small),
            "data": newly_blocked,
        }

    @mcp.tool()
    def inspect_page_for_spam(page_id: str) -> dict[str, Any]:
        """Run the spam heuristics on a specific page's cached ads and return the
        raw signal breakdown — useful for auditing why a page was (not) blocked."""
        ads = cache.load_ads(page_id=page_id, limit=1000, exclude_blocked=False)
        cls = classify_page(ads)
        page_name = next((a.get("page_name") for a in ads if a.get("page_name")), "")
        return {"page_id": page_id, "page_name": page_name, **cls}
