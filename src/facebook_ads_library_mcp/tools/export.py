"""Export a list of ads to JSON / CSV / Markdown on disk."""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

CSV_COLUMNS = [
    "id",
    "page_id",
    "page_name",
    "ad_delivery_start_time",
    "ad_delivery_stop_time",
    "publisher_platforms",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_descriptions",
    "ad_snapshot_url",
]


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _to_csv(ads: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for ad in ads:
        writer.writerow([_stringify(ad.get(col)) for col in CSV_COLUMNS])
    return buf.getvalue()


def _to_markdown(ads: list[dict[str, Any]]) -> str:
    lines = [f"# Facebook Ads export ({len(ads)} ads)\n"]
    for ad in ads:
        title = ad.get("page_name") or "Unknown page"
        lines.append(f"## {title} · `{ad.get('id')}`")
        lines.append(f"- **Page ID:** {ad.get('page_id')}")
        lines.append(
            f"- **Delivery:** {ad.get('ad_delivery_start_time')} → "
            f"{ad.get('ad_delivery_stop_time') or 'ongoing'}"
        )
        platforms = ad.get("publisher_platforms") or []
        if platforms:
            lines.append(f"- **Platforms:** {', '.join(platforms)}")
        bodies = ad.get("ad_creative_bodies") or []
        for i, body in enumerate(bodies, 1):
            lines.append(f"- **Body {i}:** {body}")
        if ad.get("ad_snapshot_url"):
            lines.append(f"- **Snapshot:** {ad['ad_snapshot_url']}")
        lines.append("")
    return "\n".join(lines)


def _resolve_path(output_path: str) -> Path:
    p = Path(output_path).expanduser()
    if not p.is_absolute():
        p = Path(os.getcwd()) / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def export_ads(
        ads: list[dict[str, Any]],
        output_path: str,
        format: Literal["json", "csv", "markdown"] = "json",
    ) -> dict[str, Any]:
        """Write a list of ad objects (as returned by `search_ads`/`search_ads_all`)
        to disk in the chosen format.

        Pass the `data` array from a previous search result. Returns the absolute
        path and byte size of the written file.
        """
        if format not in {"json", "csv", "markdown"}:
            raise ValueError("format must be json | csv | markdown")
        path = _resolve_path(output_path)
        if format == "json":
            content = json.dumps(ads, ensure_ascii=False, indent=2)
        elif format == "csv":
            content = _to_csv(ads)
        else:
            content = _to_markdown(ads)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "format": format,
            "ads_written": len(ads),
            "bytes": path.stat().st_size,
        }
