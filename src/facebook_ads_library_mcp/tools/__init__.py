"""Register MCP tools on a shared FastMCP instance."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    from . import (  # noqa: WPS433
        advanced,
        cache_admin,
        compare,
        discovery,
        export,
        landing,
        search,
        shopify,
        trends,
        validate,
    )

    search.register(mcp)
    discovery.register(mcp)
    compare.register(mcp)
    export.register(mcp)
    advanced.register(mcp)
    landing.register(mcp)
    cache_admin.register(mcp)
    shopify.register(mcp)
    trends.register(mcp)
    validate.register(mcp)
