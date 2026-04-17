"""MCP server for the Facebook Ads Library API (/ads_archive).

Docs: https://www.facebook.com/ads/library/api/
      https://developers.facebook.com/docs/graph-api/reference/ads_archive/
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import prompts as _prompts
from .client import set_token
from .tools import register_all


def _load_dotenv_if_present() -> None:
    """Best-effort .env loading; no-op if python-dotenv isn't installed."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break


mcp = FastMCP("facebook-ads-library")
register_all(mcp)
_prompts.register(mcp)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="facebook-ads-library-mcp",
        description="MCP server for the Facebook Ads Library (/ads_archive).",
    )
    parser.add_argument(
        "--token",
        help="Facebook access token (alternative to FB_ACCESS_TOKEN env var).",
        default=None,
    )
    parser.add_argument(
        "--graph-api-version",
        help="Override Graph API version (default v21.0).",
        default=None,
    )
    args = parser.parse_args()

    _load_dotenv_if_present()

    if args.graph_api_version:
        os.environ["FB_GRAPH_API_VERSION"] = args.graph_api_version
    if args.token:
        set_token(args.token)

    mcp.run()


if __name__ == "__main__":
    main()
