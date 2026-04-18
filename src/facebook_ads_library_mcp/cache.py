"""SQLite-backed local cache for ads, landing analyses, and page stats.

Default location: `~/.facebook-ads-library-mcp/cache.db`.
Override with env var `FB_ADS_CACHE_DIR`.

Design notes
------------
* Every ad returned by any search tool is persisted (upserted by Library ID).
  This lets you re-run analyses purely on the local dataset without hitting the
  API again and accumulates a longitudinal view of advertisers over time.
* Landing page analyses and per-page stats use TTL-based caching, because their
  content changes (page edits, new ads).
* SQLite is used sync — the operations are small and the FastMCP request loop
  releases the GIL during I/O.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS ads (
    id TEXT PRIMARY KEY,
    page_id TEXT,
    page_name TEXT,
    data TEXT NOT NULL,
    fetched_at INTEGER NOT NULL,
    first_seen_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ads_page_id ON ads(page_id);
CREATE INDEX IF NOT EXISTS ix_ads_fetched_at ON ads(fetched_at);
CREATE INDEX IF NOT EXISTS ix_ads_page_name ON ads(page_name);

CREATE TABLE IF NOT EXISTS landing_analyses (
    url TEXT PRIMARY KEY,
    analysis TEXT NOT NULL,
    analyzed_at INTEGER NOT NULL,
    domain TEXT,
    primary_price REAL,
    currency TEXT,
    cod_present INTEGER,
    labels TEXT,
    product_name TEXT
);
CREATE INDEX IF NOT EXISTS ix_landing_domain ON landing_analyses(domain);
CREATE INDEX IF NOT EXISTS ix_landing_currency ON landing_analyses(currency);
CREATE INDEX IF NOT EXISTS ix_landing_cod ON landing_analyses(cod_present);
CREATE INDEX IF NOT EXISTS ix_landing_price ON landing_analyses(primary_price);

CREATE TABLE IF NOT EXISTS page_stats_cache (
    cache_key TEXT PRIMARY KEY,
    stats TEXT NOT NULL,
    computed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS query_log (
    query_hash TEXT PRIMARY KEY,
    params TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    ran_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked_pages (
    page_id TEXT PRIMARY KEY,
    page_name TEXT,
    reason TEXT,
    source TEXT,
    evidence TEXT,
    added_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_blocked_reason ON blocked_pages(reason);
"""

VALID_TABLES = frozenset(
    {"ads", "landing_analyses", "page_stats_cache", "query_log", "blocked_pages"}
)


def cache_dir() -> Path:
    override = os.environ.get("FB_ADS_CACHE_DIR")
    p = Path(override).expanduser() if override else Path.home() / ".facebook-ads-library-mcp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return cache_dir() / "cache.db"


# Columns added after v0.1.0 — applied as ALTER TABLE on existing databases.
_LANDING_MIGRATIONS: list[tuple[str, str]] = [
    ("domain", "TEXT"),
    ("primary_price", "REAL"),
    ("currency", "TEXT"),
    ("cod_present", "INTEGER"),
    ("labels", "TEXT"),
    ("product_name", "TEXT"),
]


def _migrate(c: sqlite3.Connection) -> None:
    existing = {row["name"] for row in c.execute("PRAGMA table_info(landing_analyses)")}
    for col, decl in _LANDING_MIGRATIONS:
        if col not in existing:
            c.execute(f"ALTER TABLE landing_analyses ADD COLUMN {col} {decl}")


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        _migrate(c)
        yield c
        c.commit()
    finally:
        c.close()


# ---------- ads ------------------------------------------------------------ #


def save_ads(ads: list[dict[str, Any]]) -> int:
    if not ads:
        return 0
    now = int(time.time())
    rows: list[tuple[Any, ...]] = []
    for a in ads:
        ad_id = a.get("id")
        if not ad_id:
            continue
        rows.append(
            (
                str(ad_id),
                str(a.get("page_id") or ""),
                str(a.get("page_name") or ""),
                json.dumps(a, ensure_ascii=False),
                now,
                now,
            )
        )
    if not rows:
        return 0
    with _conn() as c:
        # Upsert: update data/fetched_at but keep first_seen_at from the original row.
        c.executemany(
            """
            INSERT INTO ads(id, page_id, page_name, data, fetched_at, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                page_id = excluded.page_id,
                page_name = excluded.page_name,
                data = excluded.data,
                fetched_at = excluded.fetched_at
            """,
            rows,
        )
    return len(rows)


def load_ads(
    *,
    page_id: str | None = None,
    page_ids: list[str] | None = None,
    page_name_contains: str | None = None,
    since_seconds_ago: int | None = None,
    limit: int | None = None,
    exclude_blocked: bool = True,
) -> list[dict[str, Any]]:
    sql = "SELECT data FROM ads WHERE 1=1"
    args: list[Any] = []
    if page_id:
        sql += " AND page_id = ?"
        args.append(page_id)
    if page_ids:
        placeholders = ",".join("?" for _ in page_ids)
        sql += f" AND page_id IN ({placeholders})"
        args.extend(page_ids)
    if page_name_contains:
        sql += " AND LOWER(page_name) LIKE ?"
        args.append(f"%{page_name_contains.lower()}%")
    if since_seconds_ago:
        cutoff = int(time.time()) - since_seconds_ago
        sql += " AND fetched_at >= ?"
        args.append(cutoff)
    if exclude_blocked:
        sql += " AND page_id NOT IN (SELECT page_id FROM blocked_pages)"
    sql += " ORDER BY fetched_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [json.loads(r["data"]) for r in rows]


# ---------- blocked pages ------------------------------------------------- #


def block_page(
    page_id: str,
    *,
    page_name: str = "",
    reason: str = "manual",
    source: str = "manual",
    evidence: str = "",
) -> bool:
    """Add a page_id to the block list. Returns True if newly blocked, False if
    already blocked."""
    with _conn() as c:
        existing = c.execute(
            "SELECT 1 FROM blocked_pages WHERE page_id = ?", (page_id,)
        ).fetchone()
        if existing:
            return False
        c.execute(
            """
            INSERT INTO blocked_pages(page_id, page_name, reason, source, evidence, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (page_id, page_name, reason, source, evidence, int(time.time())),
        )
    return True


def unblock_page(page_id: str) -> bool:
    """Remove a page_id from the block list. Returns True if a row was deleted."""
    with _conn() as c:
        cur = c.execute("DELETE FROM blocked_pages WHERE page_id = ?", (page_id,))
        deleted = cur.rowcount
    return deleted > 0


def list_blocked_pages(limit: int = 1000) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT page_id, page_name, reason, source, evidence, added_at
            FROM blocked_pages
            ORDER BY added_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_blocked_page_ids() -> set[str]:
    with _conn() as c:
        rows = c.execute("SELECT page_id FROM blocked_pages").fetchall()
    return {r["page_id"] for r in rows}


def is_blocked(page_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM blocked_pages WHERE page_id = ?", (page_id,)
        ).fetchone()
    return row is not None


# ---------- landing analyses ---------------------------------------------- #


def get_landing_analysis(url: str, max_age_seconds: int) -> dict[str, Any] | None:
    cutoff = int(time.time()) - max_age_seconds
    with _conn() as c:
        row = c.execute(
            "SELECT analysis FROM landing_analyses WHERE url = ? AND analyzed_at >= ?",
            (url, cutoff),
        ).fetchone()
    return json.loads(row["analysis"]) if row else None


def save_landing_analysis(url: str, analysis: dict[str, Any]) -> None:
    domain = analysis.get("domain") or ""
    primary = analysis.get("primary_price") or {}
    primary_price = primary.get("value") if isinstance(primary, dict) else None
    currency = analysis.get("currency")
    cod_present = 1 if analysis.get("cod_present") else 0
    labels = ",".join(analysis.get("labels") or [])
    product_name = analysis.get("product_name") or ""
    with _conn() as c:
        c.execute(
            """
            INSERT OR REPLACE INTO landing_analyses(
                url, analysis, analyzed_at,
                domain, primary_price, currency, cod_present, labels, product_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                json.dumps(analysis, ensure_ascii=False),
                int(time.time()),
                domain,
                primary_price,
                currency,
                cod_present,
                labels,
                product_name,
            ),
        )


def search_landings(
    *,
    domain: str | None = None,
    domain_contains: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    currency: str | None = None,
    cod_present: bool | None = None,
    label: str | None = None,
    since_seconds_ago: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Query cached landing analyses by structured columns."""
    sql = "SELECT analysis FROM landing_analyses WHERE 1=1"
    args: list[Any] = []
    if domain:
        sql += " AND domain = ?"
        args.append(domain)
    if domain_contains:
        sql += " AND domain LIKE ?"
        args.append(f"%{domain_contains.lower()}%")
    if price_min is not None:
        sql += " AND primary_price >= ?"
        args.append(price_min)
    if price_max is not None:
        sql += " AND primary_price <= ?"
        args.append(price_max)
    if currency:
        sql += " AND currency = ?"
        args.append(currency.upper())
    if cod_present is not None:
        sql += " AND cod_present = ?"
        args.append(1 if cod_present else 0)
    if label:
        sql += " AND labels LIKE ?"
        args.append(f"%{label}%")
    if since_seconds_ago:
        cutoff = int(time.time()) - since_seconds_ago
        sql += " AND analyzed_at >= ?"
        args.append(cutoff)
    sql += " ORDER BY analyzed_at DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
    return [json.loads(r["analysis"]) for r in rows]


# ---------- page stats ---------------------------------------------------- #


def get_page_stats(cache_key: str, max_age_seconds: int) -> dict[str, Any] | None:
    cutoff = int(time.time()) - max_age_seconds
    with _conn() as c:
        row = c.execute(
            "SELECT stats FROM page_stats_cache WHERE cache_key = ? AND computed_at >= ?",
            (cache_key, cutoff),
        ).fetchone()
    return json.loads(row["stats"]) if row else None


def save_page_stats(cache_key: str, stats: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO page_stats_cache(cache_key, stats, computed_at) VALUES (?, ?, ?)",
            (cache_key, json.dumps(stats, ensure_ascii=False), int(time.time())),
        )


# ---------- query log ----------------------------------------------------- #


def log_query(query_hash: str, params: dict[str, Any], result_count: int) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT OR REPLACE INTO query_log(query_hash, params, result_count, ran_at)
            VALUES (?, ?, ?, ?)
            """,
            (query_hash, json.dumps(params, ensure_ascii=False), result_count, int(time.time())),
        )


# ---------- admin --------------------------------------------------------- #


def stats() -> dict[str, Any]:
    with _conn() as c:
        ads_count = c.execute("SELECT COUNT(*) AS n FROM ads").fetchone()["n"]
        unique_pages = c.execute("SELECT COUNT(DISTINCT page_id) AS n FROM ads").fetchone()["n"]
        lp_count = c.execute("SELECT COUNT(*) AS n FROM landing_analyses").fetchone()["n"]
        ps_count = c.execute("SELECT COUNT(*) AS n FROM page_stats_cache").fetchone()["n"]
        ql_count = c.execute("SELECT COUNT(*) AS n FROM query_log").fetchone()["n"]
        oldest = c.execute("SELECT MIN(fetched_at) AS t FROM ads").fetchone()["t"]
        newest = c.execute("SELECT MAX(fetched_at) AS t FROM ads").fetchone()["t"]
    size_bytes = db_path().stat().st_size if db_path().exists() else 0
    return {
        "db_path": str(db_path()),
        "size_bytes": size_bytes,
        "ads_count": ads_count,
        "unique_pages": unique_pages,
        "landing_analyses_count": lp_count,
        "page_stats_count": ps_count,
        "query_log_count": ql_count,
        "ads_oldest_fetched_at": oldest,
        "ads_newest_fetched_at": newest,
    }


def clear(table: str | None = None) -> dict[str, Any]:
    tables = [table] if table else list(VALID_TABLES)
    cleared: dict[str, int] = {}
    for t in tables:
        if t not in VALID_TABLES:
            raise ValueError(f"Unknown table: {t}. Valid: {sorted(VALID_TABLES)}")
    with _conn() as c:
        for t in tables:
            before = c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            c.execute(f"DELETE FROM {t}")
            cleared[t] = before
    return {"cleared": cleared}
