"""MCP prompts — reusable instruction templates the calling LLM can invoke as
slash-commands. They formalise the server's intended workflow without forcing
server-side LLM calls.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.prompt()
    def research_workflow(niche: str, country_iso: str) -> str:
        """End-to-end ad-research workflow for a niche in a target country.

        Guides the assistant from keyword expansion to price aggregation.
        """
        return (
            f"Research task: find advertisers in **{country_iso}** running ads for "
            f"the **{niche}** niche, and characterise their offers.\n\n"
            "Follow these steps using the facebook-ads-library MCP tools:\n\n"
            "1. **Keyword expansion** — generate 5–10 native-language search terms "
            f"for the {niche} niche in {country_iso}'s primary language (no tool "
            "call needed, you generate these yourself). Include product synonyms "
            "and colloquial terms. For COD offers, add the local phrase for "
            "'cash on delivery'.\n\n"
            f"2. **Ad search** — for each candidate term, call `advanced_search` "
            f"with `ad_reached_countries=['{country_iso}']`, "
            "`ad_active_status='ACTIVE'`, and the term as `search_terms`. Merge "
            "results, deduping by Library ID.\n\n"
            "3. **Domain discovery** — from each ad, read `ad_creative_link_captions` "
            "and `ad_snapshot_url`. Pull out unique destination domains/URLs. "
            "Many ads on the same domain = high signal.\n\n"
            "4. **Landing-page analysis** — for each unique domain, call "
            "`analyze_landing_page`. This auto-caches for 7 days. Inspect the "
            "returned `labels`, `cod_present`, `primary_price`, and `currency`.\n\n"
            "5. **Aggregation** — call `search_cached_landings` with "
            "`cod_present=True`, `label='ecommerce'`, or a price range to "
            "produce the final answer: list advertisers + price + currency + "
            "COD yes/no.\n\n"
            "6. **Offer extraction** (optional) — for the most relevant landings, "
            "use the `extract_offer` prompt against the `text_excerpt` field to "
            "identify angle, USP, UMP, bundles, and guarantees."
        )

    @mcp.prompt()
    def extract_offer(text_excerpt: str) -> str:
        """Instructs the assistant to extract an offer/angle/USP breakdown from a
        landing-page `text_excerpt` returned by `analyze_landing_page`."""
        return (
            "You are analysing a landing page to understand its marketing offer.\n"
            "Below is the cleaned visible text of the page.\n\n"
            "Extract the following in structured JSON:\n"
            "- `product_type`: what's being sold (1–3 words)\n"
            "- `offer`: the core promise (1 sentence)\n"
            "- `price_points`: list of price + currency pairs if any are visible\n"
            "- `bundles`: any multi-pack / tiered bundle offers (list of strings)\n"
            "- `discounts`: explicit discount framings (e.g. '50% off', 'BOGO')\n"
            "- `guarantees`: money-back, satisfaction, shipping guarantees\n"
            "- `angle`: the persuasive frame (e.g. 'fear of missing out', "
            "'scientific authority', 'social proof', 'problem-solution')\n"
            "- `ump`: unique **mechanism** — the specific how/why the product works "
            "(e.g. 'patent-pending ceramic coating')\n"
            "- `usp`: unique **selling proposition** — what separates this brand "
            "from competitors (e.g. 'only vegan option in EU')\n"
            "- `urgency_signals`: countdown timers, limited stock, 'only today' type copy\n"
            "- `social_proof`: review counts, testimonials, celebrity mentions\n"
            "- `target_audience`: who the page addresses (demographic / psychographic)\n\n"
            "If a field has no evidence in the text, return `null` — do not invent.\n\n"
            f"--- LANDING TEXT EXCERPT ---\n{text_excerpt}\n--- END ---"
        )
