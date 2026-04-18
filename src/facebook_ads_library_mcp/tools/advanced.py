"""Advanced filtering, niche classification, and page-level stats."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .. import cache
from ..client import graph_get, graph_get_url
from ..constants import DEFAULT_FIELDS, LIGHT_FIELDS, VALID_PUBLISHER_PLATFORMS
from ..filters import (
    TEXT_FIELDS,
    contains_all,
    contains_any,
    days_active,
    days_since,
    extract_text,
    is_active,
    spend_bounds,
    text_length,
)
from ..taxonomy import NICHE_CATEGORIES, NICHES, PRODUCT_CONTEXT, classify


def _apply_client_filters(
    ads: list[dict[str, Any]],
    *,
    text_min_length: int | None,
    text_max_length: int | None,
    include_all_keywords: list[str] | None,
    include_any_keywords: list[str] | None,
    exclude_keywords: list[str] | None,
    brand_name_contains: str | None,
    only_active: bool,
    only_inactive: bool,
    min_days_active: int | None,
    max_days_active: int | None,
    spend_min: float | None,
    spend_max: float | None,
    spend_currency: str | None,
    niches: list[str] | None,
    product_contexts: list[str] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ad in ads:
        text = extract_text(ad)

        if text_min_length is not None and len(text) < text_min_length:
            continue
        if text_max_length is not None and len(text) > text_max_length:
            continue

        if include_all_keywords and not contains_all(text, include_all_keywords):
            continue
        if include_any_keywords and not contains_any(text, include_any_keywords):
            continue
        if exclude_keywords and contains_any(text, exclude_keywords):
            continue

        if brand_name_contains:
            name = (ad.get("page_name") or "").lower()
            if brand_name_contains.lower() not in name:
                continue

        active = is_active(ad)
        if only_active and not active:
            continue
        if only_inactive and active:
            continue

        da = days_active(ad)
        if min_days_active is not None and (da is None or da < min_days_active):
            continue
        if max_days_active is not None and (da is None or da > max_days_active):
            continue

        if spend_min is not None or spend_max is not None or spend_currency:
            lo, hi, cur = spend_bounds(ad)
            if spend_currency and (cur or "").upper() != spend_currency.upper():
                continue
            if spend_min is not None and (hi is None or hi < spend_min):
                continue
            if spend_max is not None and (lo is None or lo > spend_max):
                continue

        if niches or product_contexts:
            cls = classify(text)
            if niches:
                hits = {c["niche"] for c in cls["top_niches"]}  # type: ignore[index]
                if not hits & set(niches):
                    continue
            if product_contexts:
                hits = {c["context"] for c in cls["product_contexts"]}  # type: ignore[index]
                if not hits & set(product_contexts):
                    continue

        out.append(ad)
    return out


def _days_ago_iso(days: int) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def advanced_search(
        ad_reached_countries: list[str],
        search_terms: str | None = None,
        search_page_ids: list[str] | None = None,
        ad_active_status: Literal["ACTIVE", "ALL", "INACTIVE"] = "ALL",
        ad_type: str = "ALL",
        media_type: Literal["ALL", "IMAGE", "MEME", "VIDEO", "NONE"] = "ALL",
        publisher_platforms: list[str] | None = None,
        languages: list[str] | None = None,
        launched_min_days_ago: int | None = None,
        launched_max_days_ago: int | None = None,
        text_min_length: int | None = None,
        text_max_length: int | None = None,
        include_all_keywords: list[str] | None = None,
        include_any_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
        brand_name_contains: str | None = None,
        only_active: bool = False,
        only_inactive: bool = False,
        min_days_active: int | None = None,
        max_days_active: int | None = None,
        spend_min: float | None = None,
        spend_max: float | None = None,
        spend_currency: str | None = None,
        niches: list[str] | None = None,
        product_contexts: list[str] | None = None,
        page_size: int = 100,
        max_results: int = 500,
        max_raw_fetched: int = 2000,
        include_blocked: bool = False,
    ) -> dict[str, Any]:
        """One-shot search with server-side + client-side filtering.

        Server-side: country, search_terms, page_ids, media_type, publisher_platforms,
        languages, date window (derived from launched_*_days_ago).

        Client-side (post-filter): text length, keyword AND/OR/exclude, brand name
        substring, active/inactive, days active window, spend bands (EU political),
        niche/product-context classification, **blocked pages** (see
        `list_blocked_pages`).

        `max_raw_fetched` caps pages-fetched-before-filter so a strict filter doesn't
        paginate forever. `max_results` caps the filtered output.
        """
        if only_active and only_inactive:
            raise ValueError("only_active and only_inactive are mutually exclusive")
        if publisher_platforms:
            bad = set(publisher_platforms) - VALID_PUBLISHER_PLATFORMS
            if bad:
                raise ValueError(f"Invalid publisher_platforms: {sorted(bad)}")

        params: dict[str, Any] = {
            "ad_reached_countries": ",".join(ad_reached_countries),
            "ad_active_status": ad_active_status,
            "ad_type": ad_type,
            "media_type": media_type,
            "limit": page_size,
            "fields": ",".join(DEFAULT_FIELDS),
            "search_type": "KEYWORD_UNORDERED",
        }
        if search_terms:
            params["search_terms"] = search_terms
        if search_page_ids:
            params["search_page_ids"] = ",".join(search_page_ids)
        if publisher_platforms:
            params["publisher_platforms"] = ",".join(publisher_platforms)
        if languages:
            params["languages"] = ",".join(languages)
        if launched_max_days_ago is not None:
            params["ad_delivery_date_min"] = _days_ago_iso(launched_max_days_ago)
        if launched_min_days_ago is not None:
            params["ad_delivery_date_max"] = _days_ago_iso(launched_min_days_ago)

        raw: list[dict[str, Any]] = []
        first = await graph_get("/ads_archive", params)
        first_data = first.get("data", [])
        cache.save_ads(first_data)
        raw.extend(first_data)
        pages = 1
        next_url = first.get("paging", {}).get("next")
        while next_url and len(raw) < max_raw_fetched:
            page = await graph_get_url(next_url)
            page_data = page.get("data", [])
            cache.save_ads(page_data)
            raw.extend(page_data)
            pages += 1
            next_url = page.get("paging", {}).get("next")

        filtered = _apply_client_filters(
            raw,
            text_min_length=text_min_length,
            text_max_length=text_max_length,
            include_all_keywords=include_all_keywords,
            include_any_keywords=include_any_keywords,
            exclude_keywords=exclude_keywords,
            brand_name_contains=brand_name_contains,
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
        blocked_count = 0
        if not include_blocked:
            blocked = cache.get_blocked_page_ids()
            if blocked:
                before = len(filtered)
                filtered = [
                    a for a in filtered if str(a.get("page_id") or "") not in blocked
                ]
                blocked_count = before - len(filtered)

        truncated = False
        if len(filtered) > max_results:
            filtered = filtered[:max_results]
            truncated = True

        return {
            "raw_fetched": len(raw),
            "pages_fetched": pages,
            "filtered_count": len(filtered),
            "blocked_pages_filtered": blocked_count,
            "truncated_to_max_results": truncated,
            "data": filtered,
        }

    @mcp.tool()
    def classify_ad(text: str, top_k: int = 3) -> dict[str, Any]:
        """Classify an ad body/copy into niches + product contexts (keyword-based)."""
        return classify(text, top_k=top_k)

    @mcp.tool()
    def list_niches() -> dict[str, Any]:
        """Return the full niche taxonomy: categories, niches with keyword lists,
        and product-context tags."""
        return {
            "total_niches": len(NICHES),
            "categories": NICHE_CATEGORIES,
            "niches": NICHES,
            "product_contexts": PRODUCT_CONTEXT,
        }

    @mcp.tool()
    async def page_stats(
        page_id: str,
        ad_reached_countries: list[str],
        sample_size: int = 200,
        cache_ttl_seconds: int = 86400,
    ) -> dict[str, Any]:
        """Aggregate stats for a single Page ID across a sample of its ads.

        TTL-cached (default 24h) by `(page_id, countries, sample_size)`. Returns:
        total in sample, active/inactive split (counts + %), oldest + newest
        delivery start, median days active, platform distribution, language
        distribution, top detected niches/contexts.
        """
        cache_key = f"{page_id}|{','.join(sorted(ad_reached_countries))}|{sample_size}"
        if cache_ttl_seconds > 0:
            hit = cache.get_page_stats(cache_key, cache_ttl_seconds)
            if hit is not None:
                hit["_from_cache"] = True
                return hit

        params = {
            "ad_reached_countries": ",".join(ad_reached_countries),
            "search_page_ids": page_id,
            "ad_active_status": "ALL",
            "ad_type": "ALL",
            "limit": min(100, sample_size),
            "fields": ",".join(DEFAULT_FIELDS),
        }
        raw: list[dict[str, Any]] = []
        resp = await graph_get("/ads_archive", params)
        resp_data = resp.get("data", [])
        cache.save_ads(resp_data)
        raw.extend(resp_data)
        pages = 1
        next_url = resp.get("paging", {}).get("next")
        while next_url and len(raw) < sample_size:
            page = await graph_get_url(next_url)
            page_data = page.get("data", [])
            cache.save_ads(page_data)
            raw.extend(page_data)
            pages += 1
            next_url = page.get("paging", {}).get("next")
        raw = raw[:sample_size]

        if not raw:
            return {"page_id": page_id, "ads_in_sample": 0}

        active = sum(1 for a in raw if is_active(a))
        inactive = len(raw) - active
        starts = [a.get("ad_delivery_start_time") for a in raw if a.get("ad_delivery_start_time")]
        durations = [d for a in raw if (d := days_active(a)) is not None]
        platforms: Counter[str] = Counter()
        for a in raw:
            for p in a.get("publisher_platforms") or []:
                platforms[p] += 1
        langs: Counter[str] = Counter()
        for a in raw:
            for lg in a.get("languages") or []:
                langs[lg] += 1
        niche_counter: Counter[str] = Counter()
        context_counter: Counter[str] = Counter()
        for a in raw:
            cls = classify(extract_text(a))
            primary = cls.get("primary_niche")
            if primary:
                niche_counter[primary] += 1  # type: ignore[arg-type]
            pctx = cls.get("primary_context")
            if pctx:
                context_counter[pctx] += 1  # type: ignore[arg-type]

        durations_sorted = sorted(durations)
        median = durations_sorted[len(durations_sorted) // 2] if durations_sorted else None
        page_name = next((a.get("page_name") for a in raw if a.get("page_name")), None)

        result = {
            "page_id": page_id,
            "page_name": page_name,
            "ads_in_sample": len(raw),
            "pages_fetched": pages,
            "active_count": active,
            "inactive_count": inactive,
            "active_pct": round(100 * active / len(raw), 1),
            "inactive_pct": round(100 * inactive / len(raw), 1),
            "oldest_delivery_start": min(starts) if starts else None,
            "newest_delivery_start": max(starts) if starts else None,
            "median_days_active": median,
            "platform_distribution": dict(platforms.most_common()),
            "language_distribution": dict(langs.most_common()),
            "top_niches": dict(niche_counter.most_common(5)),
            "top_product_contexts": dict(context_counter.most_common(5)),
        }
        cache.save_page_stats(cache_key, result)
        return result
