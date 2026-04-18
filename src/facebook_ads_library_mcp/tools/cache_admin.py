"""Cache admin + cache-only search (no API calls)."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .. import cache
from .advanced import _apply_client_filters


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cache_stats() -> dict[str, Any]:
        """Return row counts, DB size, and oldest/newest ad timestamps from the
        local SQLite cache."""
        return cache.stats()

    @mcp.tool()
    def cache_clear(
        table: Literal["ads", "landing_analyses", "page_stats_cache", "query_log"] | None = None,
    ) -> dict[str, Any]:
        """Clear a single table, or all tables if `table` is omitted. Returns the
        number of rows cleared per table. Use with care — this is irreversible."""
        return cache.clear(table)

    @mcp.tool()
    def search_cached_ads(
        page_id: str | None = None,
        page_ids: list[str] | None = None,
        brand_name_contains: str | None = None,
        since_seconds_ago: int | None = None,
        text_min_length: int | None = None,
        text_max_length: int | None = None,
        include_all_keywords: list[str] | None = None,
        include_any_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        only_active: bool = False,
        only_inactive: bool = False,
        min_days_active: int | None = None,
        max_days_active: int | None = None,
        spend_min: float | None = None,
        spend_max: float | None = None,
        spend_currency: str | None = None,
        niches: list[str] | None = None,
        product_contexts: list[str] | None = None,
        max_scan: int = 10000,
        max_results: int = 500,
        include_blocked: bool = False,
    ) -> dict[str, Any]:
        """Run advanced filters over the LOCAL cache only — zero API calls.

        Use this for reanalysis: `advanced_search` etc populate the cache; this
        tool lets you re-query the same dataset with different filters without
        paying rate-limit cost.

        `since_seconds_ago` is the cutoff on `fetched_at` (e.g. 86400 for "only
        ads fetched in the last 24h"). `max_scan` caps how many rows are loaded
        before applying predicates.
        """
        loaded = cache.load_ads(
            page_id=page_id,
            page_ids=page_ids,
            page_name_contains=brand_name_contains,
            since_seconds_ago=since_seconds_ago,
            limit=max_scan,
            exclude_blocked=not include_blocked,
        )
        filtered = _apply_client_filters(
            loaded,
            text_min_length=text_min_length,
            text_max_length=text_max_length,
            include_all_keywords=include_all_keywords,
            include_any_keywords=include_any_keywords,
            exclude_keywords=exclude_keywords,
            brand_name_contains=None,  # already filtered at SQL level
            only_active=only_active,
            only_inactive=only_inactive,
            min_days_active=min_days_active,
            max_days_active=max_days_active,
            spend_min=spend_min,
            spend_max=spend_max,
            spend_currency=spend_currency,
            niches=niches,
            product_contexts=product_contexts,
        )
        truncated = False
        if len(filtered) > max_results:
            filtered = filtered[:max_results]
            truncated = True
        return {
            "scanned": len(loaded),
            "filtered_count": len(filtered),
            "truncated_to_max_results": truncated,
            "data": filtered,
        }

    @mcp.tool()
    def search_cached_landings(
        domain: str | None = None,
        domain_contains: str | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        currency: str | None = None,
        cod_present: bool | None = None,
        label: str | None = None,
        since_seconds_ago: int | None = None,
        limit: int = 200,
        include_text_excerpt: bool = False,
    ) -> dict[str, Any]:
        """Query cached landing analyses by structured fields.

        Filters: `domain` (exact), `domain_contains`, `price_min`/`price_max`,
        `currency` (ISO code), `cod_present` (bool), `label` (one of
        `ecommerce`, `cod_form`, `quiz`, `listicle`, `advertorial`),
        `since_seconds_ago` (TTL cutoff on analyzed_at).

        Returns stripped landing rows (omits `text_excerpt` by default to keep
        the payload small — set `include_text_excerpt=True` to include it).
        """
        rows = cache.search_landings(
            domain=domain,
            domain_contains=domain_contains,
            price_min=price_min,
            price_max=price_max,
            currency=currency,
            cod_present=cod_present,
            label=label,
            since_seconds_ago=since_seconds_ago,
            limit=limit,
        )
        if not include_text_excerpt:
            for r in rows:
                r.pop("text_excerpt", None)
        return {"count": len(rows), "data": rows}
