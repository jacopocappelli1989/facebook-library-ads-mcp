"""HTTP client for Graph API with retry + exponential backoff on rate limits."""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import httpx

from .constants import GRAPH_BASE, RATE_LIMIT_ERROR_CODE

_TOKEN_OVERRIDE: str | None = None


def set_token(token: str | None) -> None:
    """Override the access token at runtime (used by the CLI --token flag)."""
    global _TOKEN_OVERRIDE
    _TOKEN_OVERRIDE = token


def get_token() -> str:
    token = (
        _TOKEN_OVERRIDE
        or os.environ.get("FB_ACCESS_TOKEN")
        or os.environ.get("META_ACCESS_TOKEN")
    )
    if not token:
        raise RuntimeError(
            "Missing Facebook access token. Pass --token, set FB_ACCESS_TOKEN "
            "in the MCP server env, or put it in a .env file."
        )
    return token


class FacebookAPIError(RuntimeError):
    def __init__(self, status: int, error: dict[str, Any]) -> None:
        self.status = status
        self.code = error.get("code")
        self.message = error.get("message", "unknown error")
        self.type = error.get("type")
        self.subcode = error.get("error_subcode")
        super().__init__(
            f"Graph API {status}: {self.message} "
            f"(code={self.code}, subcode={self.subcode}, type={self.type})"
        )


async def _request(
    url: str,
    params: dict[str, Any],
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> dict[str, Any]:
    params = {**params, "access_token": get_token()}
    attempt = 0
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            resp = await client.get(url, params=params)
            try:
                data = resp.json()
            except ValueError:
                data = {"error": {"message": resp.text}}

            if resp.status_code < 400 and "error" not in data:
                return data

            err = data.get("error", {"message": resp.text})
            code = err.get("code")
            retriable = (
                resp.status_code in (429, 500, 502, 503, 504)
                or code == RATE_LIMIT_ERROR_CODE
                or code == 4  # "Application request limit reached"
                or code == 17  # "User request limit reached"
            )
            if retriable and attempt < max_retries:
                delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise FacebookAPIError(resp.status_code, err)


async def graph_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET `{GRAPH_BASE}{path}` with token + retry."""
    return await _request(f"{GRAPH_BASE}{path}", params)


async def graph_get_url(url: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET an absolute URL (e.g. the `paging.next` cursor returned by the API)."""
    return await _request(url, extra_params or {})


def join_csv(values: list[str] | None) -> str | None:
    if values is None:
        return None
    return ",".join(str(v) for v in values)
