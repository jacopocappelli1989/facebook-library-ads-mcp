"""Core search tools: search_ads, search_ads_all, next_page, get_ad, get_page_ads."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .. import cache
from ..client import graph_get, graph_get_url, join_csv
from ..constants import (
    DEFAULT_FIELDS,
    GRAPH_API_VERSION,
    LIGHT_FIELDS,
    MAX_PAGE_IDS,
    MAX_SEARCH_TERMS_LEN,
    VALID_AD_ACTIVE_STATUS,
    VALID_AD_TYPE,
    VALID_MEDIA_TYPE,
    VALID_PUBLISHER_PLATFORMS,
    VALID_SEARCH_TYPE,
)


def _build_search_params(
    *,
    ad_reached_countries: list[str],
    search_terms: str | None,
    search_page_ids: list[str] | None,
    ad_active_status: str,
    ad_type: str,
    ad_delivery_date_min: str | None,
    ad_delivery_date_max: str | None,
    media_type: str,
    publisher_platforms: list[str] | None,
    languages: list[str] | None,
    search_type: str,
    unmask_removed_content: bool,
    fields: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    if ad_active_status not in VALID_AD_ACTIVE_STATUS:
        raise ValueError(f"ad_active_status must be one of {sorted(VALID_AD_ACTIVE_STATUS)}")
    if ad_type not in VALID_AD_TYPE:
        raise ValueError(f"ad_type must be one of {sorted(VALID_AD_TYPE)}")
    if media_type not in VALID_MEDIA_TYPE:
        raise ValueError(f"media_type must be one of {sorted(VALID_MEDIA_TYPE)}")
    if search_type not in VALID_SEARCH_TYPE:
        raise ValueError(f"search_type must be one of {sorted(VALID_SEARCH_TYPE)}")
    if publisher_platforms:
        bad = set(publisher_platforms) - VALID_PUBLISHER_PLATFORMS
        if bad:
            raise ValueError(f"Invalid publisher_platforms: {sorted(bad)}")
    if search_terms and len(search_terms) > MAX_SEARCH_TERMS_LEN:
        raise ValueError(f"search_terms must be <= {MAX_SEARCH_TERMS_LEN} characters")
    if search_page_ids and len(search_page_ids) > MAX_PAGE_IDS:
        raise ValueError(f"search_page_ids accepts at most {MAX_PAGE_IDS} page IDs")

    params: dict[str, Any] = {
        "ad_reached_countries": join_csv(ad_reached_countries),
        "ad_active_status": ad_active_status,
        "ad_type": ad_type,
        "media_type": media_type,
        "search_type": search_type,
        "unmask_removed_content": "true" if unmask_removed_content else "false",
        "limit": limit,
        "fields": ",".join(fields or DEFAULT_FIELDS),
    }
    if search_terms:
        params["search_terms"] = search_terms
    if search_page_ids:
        params["search_page_ids"] = join_csv(search_page_ids)
    if ad_delivery_date_min:
        params["ad_delivery_date_min"] = ad_delivery_date_min
    if ad_delivery_date_max:
        params["ad_delivery_date_max"] = ad_delivery_date_max
    if publisher_platforms:
        params["publisher_platforms"] = join_csv(publisher_platforms)
    if languages:
        params["languages"] = join_csv(languages)

    return params


def _filter_blocked(ads: list[dict[str, Any]], blocked: set[str]) -> list[dict[str, Any]]:
    if not blocked:
        return ads
    return [a for a in ads if str(a.get("page_id") or "") not in blocked]


async def _search_ads_impl(
    *, include_blocked: bool = False, **kwargs: Any
) -> dict[str, Any]:
    params = _build_search_params(**kwargs)
    resp = await graph_get("/ads_archive", params)
    data = resp.get("data") or []
    cache.save_ads(data)  # persist all ads (including blocked ones, for history)
    if not include_blocked:
        blocked = cache.get_blocked_page_ids()
        filtered = _filter_blocked(data, blocked)
        resp = {**resp, "data": filtered, "_blocked_filtered": len(data) - len(filtered)}
    return resp


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_ads(
        ad_reached_countries: list[str],
        search_terms: str | None = None,
        search_page_ids: list[str] | None = None,
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ACTIVE",
        ad_type: str = "ALL",
        ad_delivery_date_min: str | None = None,
        ad_delivery_date_max: str | None = None,
        media_type: str = "ALL",
        publisher_platforms: list[str] | None = None,
        languages: list[str] | None = None,
        search_type: str = "KEYWORD_UNORDERED",
        unmask_removed_content: bool = False,
        fields: list[str] | None = None,
        limit: int = 25,
        include_blocked: bool = False,
    ) -> dict[str, Any]:
        """Search the Facebook Ads Library (`/ads_archive`).

        `ad_reached_countries` is REQUIRED (ISO codes like `["IT"]` or `["ALL"]`).
        Non-political ads are only returned for EU countries.

        Provide `search_terms` (≤100 chars) and/or `search_page_ids` (≤10).

        Blocked pages (see `list_blocked_pages`) are filtered out by default.
        Set `include_blocked=True` to see them.
        """
        return await _search_ads_impl(
            ad_reached_countries=ad_reached_countries,
            search_terms=search_terms,
            search_page_ids=search_page_ids,
            ad_active_status=ad_active_status,
            ad_type=ad_type,
            ad_delivery_date_min=ad_delivery_date_min,
            ad_delivery_date_max=ad_delivery_date_max,
            media_type=media_type,
            publisher_platforms=publisher_platforms,
            languages=languages,
            search_type=search_type,
            unmask_removed_content=unmask_removed_content,
            fields=fields,
            limit=limit,
            include_blocked=include_blocked,
        )

    @mcp.tool()
    async def search_ads_all(
        ad_reached_countries: list[str],
        search_terms: str | None = None,
        search_page_ids: list[str] | None = None,
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ACTIVE",
        ad_type: str = "ALL",
        ad_delivery_date_min: str | None = None,
        ad_delivery_date_max: str | None = None,
        media_type: str = "ALL",
        publisher_platforms: list[str] | None = None,
        languages: list[str] | None = None,
        search_type: str = "KEYWORD_UNORDERED",
        unmask_removed_content: bool = False,
        fields: list[str] | None = None,
        page_size: int = 100,
        max_results: int = 500,
        include_blocked: bool = False,
    ) -> dict[str, Any]:
        """Paginate through `/ads_archive` until `max_results` or the cursor ends.

        Blocked pages are filtered out by default; set `include_blocked=True`
        to see them.
        """
        all_data: list[dict[str, Any]] = []
        first = await _search_ads_impl(
            ad_reached_countries=ad_reached_countries,
            search_terms=search_terms,
            search_page_ids=search_page_ids,
            ad_active_status=ad_active_status,
            ad_type=ad_type,
            ad_delivery_date_min=ad_delivery_date_min,
            ad_delivery_date_max=ad_delivery_date_max,
            media_type=media_type,
            publisher_platforms=publisher_platforms,
            languages=languages,
            search_type=search_type,
            unmask_removed_content=unmask_removed_content,
            fields=fields,
            limit=page_size,
            include_blocked=True,  # we filter once at the end for efficiency
        )
        all_data.extend(first.get("data", []))
        pages = 1
        next_url = first.get("paging", {}).get("next")
        reason = "cursor_exhausted"
        while next_url and len(all_data) < max_results:
            page = await graph_get_url(next_url)
            page_data = page.get("data", [])
            cache.save_ads(page_data)
            all_data.extend(page_data)
            pages += 1
            next_url = page.get("paging", {}).get("next")
        if next_url and len(all_data) >= max_results:
            reason = "max_results_reached"
            all_data = all_data[:max_results]
        blocked_count = 0
        if not include_blocked:
            blocked = cache.get_blocked_page_ids()
            if blocked:
                before = len(all_data)
                all_data = _filter_blocked(all_data, blocked)
                blocked_count = before - len(all_data)
        return {
            "data": all_data,
            "fetched": len(all_data),
            "pages": pages,
            "stopped_reason": reason,
            "blocked_pages_filtered": blocked_count,
        }

    @mcp.tool()
    async def next_page(next_url: str) -> dict[str, Any]:
        """Fetch a single next page from a `paging.next` URL returned by search_ads."""
        resp = await graph_get_url(next_url)
        cache.save_ads(resp.get("data") or [])
        return resp

    @mcp.tool()
    async def get_page_ads(
        page_id: str,
        ad_reached_countries: list[str],
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ALL",
        limit: int = 25,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """All ads for a single Facebook Page ID (shortcut over search_ads)."""
        return await _search_ads_impl(
            ad_reached_countries=ad_reached_countries,
            search_terms=None,
            search_page_ids=[page_id],
            ad_active_status=ad_active_status,
            ad_type="ALL",
            ad_delivery_date_min=None,
            ad_delivery_date_max=None,
            media_type="ALL",
            publisher_platforms=None,
            languages=None,
            search_type="KEYWORD_UNORDERED",
            unmask_removed_content=False,
            fields=fields,
            limit=limit,
        )

    @mcp.tool()
    async def get_ad(ad_id: str, fields: list[str] | None = None) -> dict[str, Any]:
        """Fetch a single archived ad by its Library ID.

        The Graph API does not always expose individual ad nodes for Ad Library;
        if this errors, use `search_ads` with filters that include the ad.
        """
        params = {"fields": ",".join(fields or DEFAULT_FIELDS)}
        return await graph_get(f"/{ad_id}", params)

    @mcp.tool()
    def list_supported_fields() -> dict[str, Any]:
        """Return valid parameter enums and default/light field presets."""
        return {
            "graph_api_version": GRAPH_API_VERSION,
            "default_fields": DEFAULT_FIELDS,
            "light_fields": LIGHT_FIELDS,
            "ad_active_status": sorted(VALID_AD_ACTIVE_STATUS),
            "ad_type": sorted(VALID_AD_TYPE),
            "media_type": sorted(VALID_MEDIA_TYPE),
            "publisher_platforms": sorted(VALID_PUBLISHER_PLATFORMS),
            "search_type": sorted(VALID_SEARCH_TYPE),
        }
