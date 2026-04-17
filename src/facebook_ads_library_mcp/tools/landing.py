"""Landing page classification: ecommerce / COD form / advertorial / quiz / listicle.

Fetches a URL and runs a set of regex/substring heuristics. Returns a confidence
score per category plus the underlying signals so a caller can see *why* a page
was labelled a certain way.

The Ads Library API does NOT return the real destination URL — it returns only
`ad_snapshot_url` (a Facebook archive viewer). The caller must supply the actual
landing URL, which they typically find by opening the snapshot or by scraping it
outside of this server.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from .. import cache


# Platform signatures
ECOM_PLATFORM_SIGNATURES: dict[str, list[str]] = {
    "shopify": [
        "cdn.shopify.com", "myshopify.com", "/cart.js",
        "Shopify.shop", "shopify-features", "Shopify.theme",
    ],
    "woocommerce": [
        "woocommerce", "wc-api", "wc_add_to_cart", "add-to-cart=",
    ],
    "magento": ["Magento", "mage/cookies", "static/version"],
    "bigcommerce": ["bigcommerce.com", "stencilEditor"],
    "wix": ["wixstatic.com", "wix-stores"],
    "squarespace": ["squarespace-cdn.com", "static1.squarespace.com"],
    "prestashop": ["prestashop"],
    "clickfunnels": ["clickfunnels.com", "cfAnalytics"],
    "systeme_io": ["systeme.io"],
    "shopbase": ["shopbase.com"],
}

# Generic ecommerce signals (independent of platform)
ECOM_GENERIC = [
    "add to cart", "add to bag", "buy now", "checkout",
    "product-price", "product__price", "money", "usd", "eur",
    r"\$\s?\d", r"€\s?\d", r"£\s?\d",
    "free shipping", "in stock", "out of stock", "sku", "add_to_cart",
]

# Cash on delivery signals (multi-language: EN, IT, FR, ES, PT, AR, HI)
COD_SIGNALS = [
    "cash on delivery", "pay on delivery", "c.o.d.", " cod ",
    "pagamento alla consegna", "contrassegno",
    "paiement à la livraison", "paiement a la livraison",
    "pago contra entrega", "contra reembolso",
    "pagamento na entrega",
    "الدفع عند الاستلام",
    "कैश ऑन डिलीवरी",
]

# Form fields expected on a typical COD landing
COD_FORM_FIELD_SIGNALS = [
    "name=\"name\"", "name='name'", "name=\"full_name\"", "name='full_name'",
    "name=\"phone\"", "name='phone'", "name=\"mobile\"", "name='mobile'",
    "name=\"address\"", "name='address'", "name=\"city\"", "name='city'",
    "name=\"postal\"", "name=\"zip\"",
]

# Quiz page signals
QUIZ_SIGNALS = [
    "quiz", "take the quiz", "start quiz", "question 1", "step 1 of",
    "multiple choice", "next question",
    "class=\"quiz", "data-quiz", "role=\"radiogroup\"",
    "which of the following", "which best describes",
]

# Listicle signals
LISTICLE_SIGNALS = [
    "top 5 ", "top 10 ", "top 7 ", "top 3 ", "best 5 ", "best 10 ",
    "7 reasons", "10 reasons", "5 reasons", "5 tips", "10 tips",
    "<h2>1.", "<h3>1.", "<h2>1 ", "<h3>1 ", "<li>", "<ol>",
]

# Advertorial signals — editorial framing + CTA
ADVERTORIAL_SIGNALS = [
    "by staff reporter", "sponsored content", "sponsored post", "paid partnership",
    "advertorial", "editorial staff", "special report",
    "disclaimer:", "this is a sponsored",
    "published on", "updated on", "as seen on",
]


def _count_hits(text: str, signals: list[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    for sig in signals:
        if sig.startswith("\\") or any(c in sig for c in ".?*+[]()"):
            try:
                if re.search(sig, text, flags=re.IGNORECASE):
                    hits.append(sig)
            except re.error:
                if sig.lower() in text.lower():
                    hits.append(sig)
        else:
            if sig.lower() in text.lower():
                hits.append(sig)
    return len(hits), hits


def _detect_platform(html: str) -> list[str]:
    found: list[str] = []
    for platform, sigs in ECOM_PLATFORM_SIGNATURES.items():
        for sig in sigs:
            if sig.lower() in html.lower():
                found.append(platform)
                break
    return found


def _has_form(html: str) -> bool:
    return bool(re.search(r"<form[\s>]", html, flags=re.IGNORECASE))


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def analyze_landing_page(
        url: str,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
        follow_redirects: bool = True,
        timeout_seconds: float = 20.0,
        cache_ttl_seconds: int = 604800,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Fetch `url` and classify the landing page into ecommerce / COD-form /
        advertorial / quiz / listicle categories based on HTML heuristics.

        Cached locally for `cache_ttl_seconds` (default 7 days). Pass
        `force_refresh=True` to re-fetch even if a fresh cache entry exists.
        """
        if not force_refresh and cache_ttl_seconds > 0:
            hit = cache.get_landing_analysis(url, cache_ttl_seconds)
            if hit is not None:
                hit["_from_cache"] = True
                return hit

        headers = {"User-Agent": user_agent, "Accept-Language": "en,it;q=0.8"}
        try:
            async with httpx.AsyncClient(
                follow_redirects=follow_redirects, timeout=timeout_seconds
            ) as client:
                resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            return {"url": url, "error": f"fetch failed: {exc}"}

        html = resp.text or ""
        final_url = str(resp.url)

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        title = (title_match.group(1).strip() if title_match else "")[:300]

        platforms = _detect_platform(html)
        ecom_generic_score, ecom_hits = _count_hits(html, ECOM_GENERIC)
        cod_text_score, cod_text_hits = _count_hits(html, COD_SIGNALS)
        cod_form_score, cod_form_hits = _count_hits(html, COD_FORM_FIELD_SIGNALS)
        quiz_score, quiz_hits = _count_hits(html, QUIZ_SIGNALS)
        listicle_score, listicle_hits = _count_hits(html, LISTICLE_SIGNALS)
        adv_score, adv_hits = _count_hits(html, ADVERTORIAL_SIGNALS)

        is_ecommerce = bool(platforms) or ecom_generic_score >= 3
        has_form = _has_form(html)
        is_cod_form = has_form and (cod_text_score >= 1 or cod_form_score >= 3)
        is_quiz = quiz_score >= 2 and has_form
        is_listicle = listicle_score >= 2 and len(html) > 5000
        is_advertorial = adv_score >= 2 and len(html) > 5000

        labels: list[str] = []
        if is_ecommerce:
            labels.append("ecommerce")
        if is_cod_form:
            labels.append("cod_form")
        if is_quiz:
            labels.append("quiz")
        if is_listicle:
            labels.append("listicle")
        if is_advertorial:
            labels.append("advertorial")
        if not labels:
            labels.append("unclassified")

        result = {
            "url": url,
            "final_url": final_url,
            "http_status": resp.status_code,
            "title": title,
            "labels": labels,
            "has_form": has_form,
            "ecommerce": {
                "is_ecommerce": is_ecommerce,
                "platforms_detected": platforms,
                "generic_signal_score": ecom_generic_score,
                "generic_signals_matched": ecom_hits[:10],
            },
            "cod_form": {
                "is_cod_form": is_cod_form,
                "text_signal_score": cod_text_score,
                "text_signals_matched": cod_text_hits,
                "form_field_score": cod_form_score,
                "form_fields_matched": cod_form_hits,
            },
            "quiz": {
                "is_quiz": is_quiz,
                "score": quiz_score,
                "signals_matched": quiz_hits,
            },
            "listicle": {
                "is_listicle": is_listicle,
                "score": listicle_score,
                "signals_matched": listicle_hits,
            },
            "advertorial": {
                "is_advertorial": is_advertorial,
                "score": adv_score,
                "signals_matched": adv_hits,
            },
            "html_bytes": len(html),
        }
        cache.save_landing_analysis(url, result)
        return result
