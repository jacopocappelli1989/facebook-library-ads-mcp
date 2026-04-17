"""Shared constants: Graph API version, default fields, enum whitelists."""

from __future__ import annotations

import os

GRAPH_API_VERSION = os.environ.get("FB_GRAPH_API_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

DEFAULT_FIELDS: list[str] = [
    "id",
    "ad_creation_time",
    "ad_creative_bodies",
    "ad_creative_link_captions",
    "ad_creative_link_descriptions",
    "ad_creative_link_titles",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "ad_snapshot_url",
    "bylines",
    "currency",
    "delivery_by_region",
    "demographic_distribution",
    "estimated_audience_size",
    "eu_total_reach",
    "impressions",
    "languages",
    "page_id",
    "page_name",
    "publisher_platforms",
    "spend",
    "target_ages",
    "target_gender",
    "target_locations",
]

LIGHT_FIELDS: list[str] = [
    "id",
    "page_id",
    "page_name",
    "ad_snapshot_url",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "publisher_platforms",
    "ad_creative_bodies",
]

VALID_AD_ACTIVE_STATUS = frozenset({"ACTIVE", "ALL", "INACTIVE"})
VALID_AD_TYPE = frozenset(
    {
        "ALL",
        "EMPLOYMENT_ADS",
        "FINANCIAL_PRODUCTS_AND_SERVICES_ADS",
        "HOUSING_ADS",
        "POLITICAL_AND_ISSUE_ADS",
    }
)
VALID_MEDIA_TYPE = frozenset({"ALL", "IMAGE", "MEME", "VIDEO", "NONE"})
VALID_PUBLISHER_PLATFORMS = frozenset(
    {
        "FACEBOOK",
        "INSTAGRAM",
        "AUDIENCE_NETWORK",
        "MESSENGER",
        "WHATSAPP",
        "OCULUS",
        "THREADS",
    }
)
VALID_SEARCH_TYPE = frozenset({"KEYWORD_UNORDERED", "KEYWORD_EXACT_PHRASE"})

RATE_LIMIT_ERROR_CODE = 613
MAX_PAGE_IDS = 10
MAX_SEARCH_TERMS_LEN = 100
