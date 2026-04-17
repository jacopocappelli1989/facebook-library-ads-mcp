"""Shopify-store inspection: theme name + product count via public endpoints.

Shopify exposes `/products.json` on every store unless the merchant explicitly
disables it. We also scrape the storefront HTML for `Shopify.theme.name` which
every theme injects.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

_THEME_NAME_PATTERNS = [
    re.compile(r"Shopify\.theme\s*=\s*\{[^}]*?\"name\"\s*:\s*\"([^\"]+)\"", re.IGNORECASE | re.DOTALL),
    re.compile(r"Shopify\.theme\.name\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE),
    re.compile(r"theme_name\s*:\s*[\"']([^\"']+)[\"']", re.IGNORECASE),
]

_SHOPIFY_MARKERS = ("cdn.shopify.com", "myshopify.com", "Shopify.shop", "shopify-features")


def _normalise_domain(domain_or_url: str) -> str:
    s = domain_or_url.strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    parsed = urlparse(s)
    host = (parsed.netloc or parsed.path).lower()
    return host.removeprefix("www.")


async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
    except httpx.HTTPError:
        return None


def _min_variant_price(product: dict[str, Any]) -> float | None:
    prices: list[float] = []
    for v in product.get("variants") or []:
        raw = v.get("price")
        if raw is None:
            continue
        try:
            prices.append(float(raw))
        except (TypeError, ValueError):
            continue
    return min(prices) if prices else None


async def inspect_shopify_store(
    domain: str,
    *,
    product_sample_size: int = 250,
    max_pages: int = 8,
    timeout_seconds: float = 20.0,
    include_sample_products: bool = True,
) -> dict[str, Any]:
    """Reusable helper (not MCP-registered) for `check_shopify_store` and
    `validate_competitor` to share the same implementation."""
    host = _normalise_domain(domain)
    if not host:
        return {"domain": domain, "error": "empty domain"}
    base = f"https://{host}"

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout_seconds
    ) as client:
        home = await _fetch(client, base)
        html = (home.text or "") if home is not None else ""
        is_shopify = any(m.lower() in html.lower() for m in _SHOPIFY_MARKERS)

        theme_name: str | None = None
        for pat in _THEME_NAME_PATTERNS:
            m = pat.search(html)
            if m:
                theme_name = m.group(1).strip()
                break

        products: list[dict[str, Any]] = []
        pages_fetched = 0
        products_json_accessible = False
        last_status: int | None = None
        for page_idx in range(1, max_pages + 1):
            url = f"{base}/products.json?limit={product_sample_size}&page={page_idx}"
            resp = await _fetch(client, url)
            if resp is None:
                break
            last_status = resp.status_code
            if resp.status_code != 200:
                break
            try:
                payload = resp.json()
            except ValueError:
                break
            products_json_accessible = True
            batch = payload.get("products") or []
            if not batch:
                break
            products.extend(batch)
            pages_fetched += 1
            if len(batch) < product_sample_size:
                break

    uniq_handles: set[str] = {p.get("handle") or str(p.get("id")) for p in products}
    result: dict[str, Any] = {
        "domain": host,
        "is_shopify": is_shopify,
        "home_http_status": home.status_code if home is not None else None,
        "theme_name": theme_name,
        "products_json_accessible": products_json_accessible,
        "products_json_last_status": last_status,
        "pages_fetched": pages_fetched,
        "product_count": len(uniq_handles),
        "product_count_is_lower_bound": pages_fetched == max_pages,
    }
    if include_sample_products:
        result["sample_products"] = [
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "handle": p.get("handle"),
                "variants_count": len(p.get("variants") or []),
                "min_price": _min_variant_price(p),
            }
            for p in products[:10]
        ]
    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def check_shopify_store(
        domain: str,
        product_sample_size: int = 250,
        max_pages: int = 8,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Inspect a Shopify store: theme name + product catalogue size.

        Probes:
        - `GET /` — extracts `Shopify.theme.name` from the storefront HTML
          and confirms the site is actually Shopify.
        - `GET /products.json?limit=250&page=N` (paginated up to `max_pages`,
          default 8 → up to 2000 products). The endpoint may be disabled by
          the merchant — then `products_json_accessible=False`.

        Returns raw numbers — no pass/fail verdicts. If `pages_fetched` hits
        `max_pages`, `product_count` is a lower bound (flagged via
        `product_count_is_lower_bound=True`).
        """
        return await inspect_shopify_store(
            domain,
            product_sample_size=product_sample_size,
            max_pages=max_pages,
            timeout_seconds=timeout_seconds,
            include_sample_products=True,
        )
