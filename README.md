# facebook-ads-library-mcp

An MCP (Model Context Protocol) server for the official [Facebook Ads Library API](https://www.facebook.com/ads/library/api/) (`/ads_archive` on Graph API). Built for ad research, competitor spying, and creative intelligence workflows in Claude Code, Claude Desktop, Cursor, or any MCP-compatible client.

## Highlights

- **17 tools** across search, discovery, competitive analysis, niche classification (**120 niches / 15 categories**), landing-page classification, export, and local cache admin
- **Local SQLite cache**: every ad fetched is upserted to disk; re-run analyses with different filters without re-hitting the API. TTL caches for landing-page analyses (7 days) and page stats (24h)
- **Advanced client-side filtering** for criteria the Graph API doesn't natively support: text length, AND/OR/exclude keywords, brand-name substring, days-active window, spend bands (EUR), niche, product context
- **Auto-pagination** with a hard cap so strict filters don't paginate forever
- **Retry + exponential backoff** on Graph rate-limit codes (`613`, `4`, `17`, HTTP `429`/`5xx`)
- **Landing-page classifier** detects Shopify / WooCommerce / Magento / Wix / ClickFunnels / Systeme.io plus COD forms, advertorials, quizzes, and listicles

## Tools

### Search
| Tool | Purpose |
|---|---|
| `search_ads` | Single-page search with all official filters (country, search_terms, page_ids, date window, media_type, platforms, languages) |
| `search_ads_all` | Auto-paginate until `max_results` (default 500) |
| `next_page` | Follow a `paging.next` URL manually |
| `get_page_ads` | Shortcut for a single Page ID |
| `get_ad` | Detail for a single archived ad by Library ID |
| `list_supported_fields` | Dump valid enum values and field presets |

### Advanced search (client-side filters)
| Tool | Purpose |
|---|---|
| `advanced_search` | One-shot search with **server + client** filtering: text length, keyword AND/OR/exclude, brand name, active/inactive, days-active window, spend EUR bands, launched X–Y days ago, niche, product context |
| `classify_ad` | Classify an ad body into niches + product context (keyword-based) |
| `list_niches` | Dump the full taxonomy (categories → niches → keyword lists) |

### Discovery & competitive
| Tool | Purpose |
|---|---|
| `find_pages_by_name` | Resolve a brand name into candidate Page IDs by sampling ads |
| `compare_brands` | Parallel fetch for up to 20 Page IDs + per-brand summary (counts, active/inactive, platform mix) |
| `page_stats` | Aggregate stats for one Page ID: total in sample, active %, oldest/newest delivery start, median days active, platform/language/niche distribution |

### Landing page
| Tool | Purpose |
|---|---|
| `analyze_landing_page` | Fetch a URL and classify as **ecommerce** (Shopify / WooCommerce / Magento / Wix / ClickFunnels / Systeme.io / …), **COD form**, **advertorial**, **quiz**, **listicle**. Returns labels + per-category scores and matched signals |

### Export
| Tool | Purpose |
|---|---|
| `export_ads` | Save an array of ads to disk in `json`, `csv`, or `markdown` |

### Local cache (SQLite)
| Tool | Purpose |
|---|---|
| `search_cached_ads` | Advanced filters on the local cache only — **zero API calls** |
| `cache_stats` | Row counts, DB size, oldest/newest ad timestamps |
| `cache_clear(table?)` | Clear a specific table (`ads`, `landing_analyses`, `page_stats_cache`, `query_log`) or all |

**Automatic caching**:
- Every ad returned by any search tool is upserted into `ads` (PK = Library ID)
- `analyze_landing_page` is TTL-cached (default 7 days; bypass with `force_refresh=True`)
- `page_stats` is TTL-cached (default 24h)
- Default DB: `~/.facebook-ads-library-mcp/cache.db` — override with env `FB_ADS_CACHE_DIR`

## Filter criteria mapping

| Criterion | How to filter |
|---|---|
| 1. Ad text length | `advanced_search(text_min_length, text_max_length)` |
| 2. Words in the text | `include_all_keywords`, `include_any_keywords`, `exclude_keywords` |
| 3. Product context / offer type | `product_contexts=["physical_product", "cod_payment", …]` or `classify_ad(text)` |
| 4. Image or video | `media_type="IMAGE" | "VIDEO"` (server-side) |
| 5. Brand name | `brand_name_contains="nike"` or `search_page_ids=[…]` |
| 6. Landing: ecommerce / COD / advertorial / quiz / listicle | `analyze_landing_page(url)` → `labels: […]` |
| 7. EU spend bands | `spend_min`, `spend_max`, `spend_currency="EUR"` (political/issue ads only) |
| 8. Days active | `min_days_active`, `max_days_active` |
| 9. Ads per page, active/inactive % | `page_stats(page_id)` |
| 10. Launched X–Y days ago | `launched_min_days_ago`, `launched_max_days_ago` (server-side) |
| 11. Niche | `niches=[…]` — 120 niches across 15 categories |

## Niches

**120 niches across 15 categories**: apparel, supplements_health, beauty, home, kids_baby, pets, sports_outdoor, hobbies, food_drink, automotive, tech, lifestyle, info_services, seasonal, adult.

A few examples per category:

| Category | Niches (partial) |
|---|---|
| apparel | clothes_womens/mens/baby, shoes, jewelry, watches, bags_purses, eyewear |
| supplements_health | supplements, weight_loss, anti_aging, joint_pain, menopause, sleep_aids, cbd, biohacking |
| beauty | skincare, makeup, haircare, fragrance, nails |
| home | home_decor, lights, mattresses_bedding, kitchen_cookware, kitchen_gadgets |
| pets | pets_dog, pets_cat, pets_chicken, pets_rabbit, pets_horse, pets_bird_fish |
| sports_outdoor | pickleball, golf, fishing, hunting, camping_hiking, rv_van_life, yoga_pilates |
| hobbies | gardening, woodworking, quilting_knitting, photography_gear, 3d_printing |
| info_services | online_course, real_estate_investing, ecom_dropshipping_course, crypto, trading_investing, saas_software |
| lifestyle | religion_christian, grey_hair_silver, empty_nesters, veterans, wedding |

**9 product contexts**: `physical_product`, `digital_info_product`, `service`, `subscription`, `cod_payment`, `discount_offer`, `free_trial_or_sample`, `lead_gen_form`, `app_install`.

Use `list_niches` to see every keyword. Keywords are mostly English (with Italian hints for COD) — extend [`taxonomy.py`](src/facebook_ads_library_mcp/taxonomy.py) to target other languages.

## Project layout

```
src/facebook_ads_library_mcp/
├── server.py          # FastMCP + CLI entrypoint
├── client.py          # HTTP client with retry/backoff
├── constants.py       # Enum whitelists, default fields
├── cache.py           # SQLite cache (ads / landing / page_stats / query_log)
├── filters.py         # Predicates: length, keywords, days, spend, active status
├── taxonomy.py        # 120 niches + 9 product contexts
└── tools/
    ├── search.py      # search_ads, search_ads_all, next_page, get_page_ads, get_ad, list_supported_fields
    ├── discovery.py   # find_pages_by_name
    ├── compare.py     # compare_brands
    ├── advanced.py    # advanced_search, classify_ad, list_niches, page_stats
    ├── landing.py     # analyze_landing_page (TTL-cached)
    ├── export.py      # export_ads
    └── cache_admin.py # search_cached_ads, cache_stats, cache_clear
```

## Setup

Requires Python ≥ 3.10 and a Facebook Graph API access token with `ads_read` scope (generate one from [Graph API Explorer](https://developers.facebook.com/tools/explorer/)).

```bash
git clone https://github.com/jacopocappelli1989/facebook-library-ads-mcp.git
cd facebook-library-ads-mcp
uv sync
cp .env.example .env       # paste your token into .env
```

Token precedence: `--token` CLI flag → `FB_ACCESS_TOKEN` (or `META_ACCESS_TOKEN`) env var → `.env` file.

Graph API version: `FB_GRAPH_API_VERSION` env var (default `v21.0`) or `--graph-api-version` CLI flag.

## Run

```bash
# With .env
uv run facebook-ads-library-mcp

# With CLI flag
uv run facebook-ads-library-mcp --token YOUR_TOKEN_HERE

# As a module
uv run python -m facebook_ads_library_mcp
```

## Docker

```bash
docker build -t fb-ads-mcp .
docker run -i --rm -e FB_ACCESS_TOKEN=YOUR_TOKEN_HERE fb-ads-mcp
```

Bind-mount a cache volume to persist across containers:

```bash
docker run -i --rm \
  -e FB_ACCESS_TOKEN=YOUR_TOKEN_HERE \
  -e FB_ADS_CACHE_DIR=/cache \
  -v $HOME/.facebook-ads-library-mcp:/cache \
  fb-ads-mcp
```

## Claude Code / Desktop configuration

CLI:

```bash
claude mcp add facebook-ads-library \
  -e FB_ACCESS_TOKEN=YOUR_TOKEN_HERE \
  -- uv --directory /absolute/path/to/facebook-library-ads-mcp run facebook-ads-library-mcp
```

Or JSON (`~/.claude.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "facebook-ads-library": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/facebook-library-ads-mcp",
        "run",
        "facebook-ads-library-mcp"
      ],
      "env": { "FB_ACCESS_TOKEN": "YOUR_TOKEN_HERE" }
    }
  }
}
```

## Examples

**Advanced search — supplement video ads in Italy, active 30–180 days, with a discount:**

```json
{
  "ad_reached_countries": ["IT"],
  "search_terms": "benessere",
  "media_type": "VIDEO",
  "niches": ["supplements", "holistic_wellness"],
  "product_contexts": ["discount_offer"],
  "min_days_active": 30,
  "max_days_active": 180,
  "text_min_length": 150,
  "only_active": true,
  "exclude_keywords": ["gratis", "omaggio"],
  "launched_max_days_ago": 365
}
```

**From brand name to page_id to full profile:**

```json
find_pages_by_name({ "brand_name": "Intimissimi", "ad_reached_countries": ["IT"] })
page_stats({ "page_id": "<id>", "ad_reached_countries": ["IT"], "sample_size": 200 })
```

**Classify a landing page:**

```json
analyze_landing_page({ "url": "https://www.allbirds.com/products/mens-wool-runners" })
// → labels: ["ecommerce"], platforms_detected: ["shopify"], generic_signal_score: 11
```

**Compare competitors:**

```json
compare_brands({
  "page_ids": ["<nike>", "<adidas>", "<puma>"],
  "ad_reached_countries": ["IT"],
  "ad_active_status": "ACTIVE"
})
```

**Re-analyze without extra API calls:**

```json
search_cached_ads({
  "niches": ["supplements"],
  "only_active": true,
  "text_min_length": 100,
  "since_seconds_ago": 86400
})
```

## Notes & caveats

- The Ads Library API returns `ad_snapshot_url` (a Meta archive viewer), **not** the actual destination URL. Pass the real landing URL explicitly to `analyze_landing_page`.
- The `spend` field is populated only for political / issue ads in the EU.
- For non-political ads, `ad_reached_countries` must include EU country codes to get any results.
- Client-side filters require fetching ads first. `advanced_search` caps pages-before-filter at `max_raw_fetched` (default 2000) so a tight filter can't paginate indefinitely.
- Retry policy: 3 attempts with `2s × 2^n + jitter` backoff on error codes `613` (rate limit), `4`, `17`, HTTP `429`/`5xx`.

## Credits

Built as a from-scratch Python / FastMCP implementation of the Ads Library API with inspiration from [proxy-intell/facebook-ads-library-mcp](https://github.com/proxy-intell/facebook-ads-library-mcp) (ScrapeCreators + Gemini approach) and [RamsesAguirre777/facebook-ads-library-mcp](https://github.com/RamsesAguirre777/facebook-ads-library-mcp) (direct Graph API approach). This project uses the official Graph API directly — no third-party scrapers, no image/video AI dependencies — and adds persistent local caching, an expanded niche taxonomy, and a landing-page classifier.

## License

MIT
