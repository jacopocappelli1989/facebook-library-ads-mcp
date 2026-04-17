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

# Cash on delivery signals (multi-language)
COD_SIGNALS = [
    # EN
    "cash on delivery", "pay on delivery", "c.o.d.", " cod ",
    "cod available", "pay when you receive",
    # IT
    "pagamento alla consegna", "contrassegno", "paga alla consegna",
    # FR
    "paiement à la livraison", "paiement a la livraison",
    "contre remboursement",
    # ES
    "pago contra entrega", "contra reembolso", "pago al recibir",
    # PT
    "pagamento na entrega", "pagar na entrega",
    # DE
    "nachnahme", "zahlung bei lieferung", "bei lieferung bezahlen",
    # PL
    "za pobraniem", "płatność przy odbiorze", "platnosc przy odbiorze",
    "zapłać przy odbiorze",
    # NL
    "rembours", "betaling bij aflevering",
    # SE/NO/DK
    "betala vid leverans", "betal ved levering",
    # RO
    "ramburs", "plata la livrare",
    # RU
    "наложенным платежом", "оплата при получении",
    # AR
    "الدفع عند الاستلام",
    # HI
    "कैश ऑन डिलीवरी",
    # TR
    "kapıda ödeme",
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


# Price extraction.
# Regex matches patterns like: "€12,99", "12.99 EUR", "$1,234.56", "49 zł", "1299 PLN".
# Handles decimal separators `.` and `,`, optional thousands separators, and either
# currency-prefix or currency-suffix layouts.
_CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₽": "RUB",
    "₺": "TRY",
    "₹": "INR",
    "zł": "PLN",
    "Kč": "CZK",
    "kr": "SEK",
    "R$": "BRL",
}

_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "RUB", "TRY", "INR", "PLN", "CZK", "SEK",
    "BRL", "CHF", "AUD", "CAD", "NZD", "NOK", "DKK", "RON", "HUF", "BGN",
    "HRK", "ILS", "AED", "SAR", "MXN", "COP", "CLP", "ARS",
}

_PRICE_RE_SYMBOL_PREFIX = re.compile(
    r"(R\$|zł|Kč|kr|[$€£¥₽₺₹])\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)",
    flags=re.IGNORECASE,
)
_PRICE_RE_SYMBOL_SUFFIX = re.compile(
    r"(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)\s*(zł|Kč|kr|R\$|[$€£¥₽₺₹])",
    flags=re.IGNORECASE,
)
_PRICE_RE_CODE_SUFFIX = re.compile(
    r"(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)\s*(USD|EUR|GBP|JPY|RUB|TRY|INR|PLN|CZK|SEK|BRL|CHF|AUD|CAD|NZD|NOK|DKK|RON|HUF|BGN|HRK|ILS|AED|SAR|MXN|COP|CLP|ARS)\b"
)
_PRICE_RE_CODE_PREFIX = re.compile(
    r"(USD|EUR|GBP|JPY|RUB|TRY|INR|PLN|CZK|SEK|BRL|CHF|AUD|CAD|NZD|NOK|DKK|RON|HUF|BGN|HRK|ILS|AED|SAR|MXN|COP|CLP|ARS)\s*(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?)"
)


def _parse_price_number(raw: str) -> float | None:
    """Normalise a raw price string to a float.

    Handles European (`1.299,99` or `1 299,99`), US (`1,299.99`), and plain
    (`1299.99`, `1299,99`) formats. Falls back to None if ambiguous.
    """
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        # Whichever separator comes last is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Use `,` as decimal if it plausibly separates ≤2 fractional digits.
        if re.match(r"^\d+,\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _normalise_currency(raw: str) -> str | None:
    r = raw.strip()
    if r in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[r]
    upper = r.upper()
    if upper in _CURRENCY_CODES:
        return upper
    return _CURRENCY_SYMBOLS.get(r, None)


def _extract_prices(html: str, max_items: int = 40) -> list[dict[str, Any]]:
    """Scan the HTML for price-like substrings. Returns unique entries by
    (value, currency) pair, preserving the original match text."""
    seen: set[tuple[float, str]] = set()
    out: list[dict[str, Any]] = []

    def _try_add(raw_num: str, cur_raw: str) -> None:
        value = _parse_price_number(raw_num)
        currency = _normalise_currency(cur_raw)
        if value is None or currency is None or value <= 0:
            return
        key = (round(value, 2), currency)
        if key in seen:
            return
        seen.add(key)
        out.append({"value": round(value, 2), "currency": currency, "raw": f"{raw_num} {cur_raw}".strip()})

    for match in _PRICE_RE_SYMBOL_PREFIX.finditer(html):
        _try_add(match.group(2), match.group(1))
        if len(out) >= max_items:
            return out
    for match in _PRICE_RE_SYMBOL_SUFFIX.finditer(html):
        _try_add(match.group(1), match.group(2))
        if len(out) >= max_items:
            return out
    for match in _PRICE_RE_CODE_SUFFIX.finditer(html):
        _try_add(match.group(1), match.group(2))
        if len(out) >= max_items:
            return out
    for match in _PRICE_RE_CODE_PREFIX.finditer(html):
        _try_add(match.group(2), match.group(1))
        if len(out) >= max_items:
            return out
    return out


def _primary_price(prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Heuristic: pick the most common currency, then the *median* price in
    that currency (more robust than mean to shipping/discount noise)."""
    if not prices:
        return None
    from collections import Counter

    counter: Counter[str] = Counter(p["currency"] for p in prices)
    primary_currency, _ = counter.most_common(1)[0]
    values = sorted(p["value"] for p in prices if p["currency"] == primary_currency)
    median = values[len(values) // 2]
    return {"value": median, "currency": primary_currency}


_OG_TITLE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
    flags=re.IGNORECASE,
)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", flags=re.IGNORECASE | re.DOTALL)
_TAGS_RE = re.compile(r"<[^>]+>")


def _extract_product_name(html: str, fallback_title: str) -> str:
    m = _OG_TITLE_RE.search(html)
    if m:
        return m.group(1).strip()[:300]
    m = _H1_RE.search(html)
    if m:
        return _TAGS_RE.sub("", m.group(1)).strip()[:300]
    return fallback_title[:300]


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).netloc.lower()
        return host.removeprefix("www.")
    except (ValueError, AttributeError):
        return ""


_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _visible_text(html: str, max_chars: int = 8000) -> str:
    """Strip scripts/styles/tags and collapse whitespace into a readable excerpt.

    The excerpt is meant to be short enough to send back to a calling LLM for
    semantic extraction (angle, USP, UMP, bundles, mechanism, etc.) without
    blowing up the caller's context window.
    """
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    cleaned = _TAGS_RE.sub("\n", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = cleaned.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    lines = [_WS_RE.sub(" ", ln).strip() for ln in cleaned.splitlines()]
    lines = [ln for ln in lines if ln]
    excerpt = "\n".join(lines)
    excerpt = _MULTI_NL_RE.sub("\n\n", excerpt)
    if len(excerpt) > max_chars:
        # Head + tail sampling keeps hero + CTA/footer context.
        head = excerpt[: int(max_chars * 0.7)]
        tail = excerpt[-int(max_chars * 0.3):]
        excerpt = f"{head}\n\n[...truncated...]\n\n{tail}"
    return excerpt


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def analyze_landing_page(
        url: str,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
        follow_redirects: bool = True,
        timeout_seconds: float = 20.0,
        cache_ttl_seconds: int = 604800,
        force_refresh: bool = False,
        include_text_excerpt: bool = True,
        text_excerpt_max_chars: int = 8000,
    ) -> dict[str, Any]:
        """Fetch `url`, classify the landing page, and extract structured fields.

        Classifies into: **ecommerce** (Shopify/Woo/Magento/Wix/ClickFunnels/…),
        **cod_form**, **advertorial**, **quiz**, **listicle**.

        Extracts: `prices[]`, `primary_price`, `currency`, `domain`,
        `product_name`, `cod_present` bool, `title`, detected platforms.

        If `include_text_excerpt=True`, returns a cleaned visible-text excerpt
        (`text_excerpt`) so the calling LLM can do semantic extraction of
        offer/angle/USP/UMP/bundles/guarantees in its own reasoning step.

        Cached locally for `cache_ttl_seconds` (default 7 days). Pass
        `force_refresh=True` to re-fetch.
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
        domain = _domain_of(final_url)

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
        cod_present = cod_text_score >= 1 or cod_form_score >= 3

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

        prices = _extract_prices(html)
        primary = _primary_price(prices)
        product_name = _extract_product_name(html, title)

        result: dict[str, Any] = {
            "url": url,
            "final_url": final_url,
            "domain": domain,
            "http_status": resp.status_code,
            "title": title,
            "product_name": product_name,
            "labels": labels,
            "has_form": has_form,
            "cod_present": cod_present,
            "prices": prices,
            "primary_price": primary,
            "currency": primary["currency"] if primary else None,
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
        if include_text_excerpt:
            result["text_excerpt"] = _visible_text(html, max_chars=text_excerpt_max_chars)
        cache.save_landing_analysis(url, result)
        return result
