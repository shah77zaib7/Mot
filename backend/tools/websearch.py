"""web_search — text results via ddgs, no API key. Read-only.

5-minute cache, 8 s timeout, and if ddgs fails we fall back to searching the
RSS pool so a rate limit never turns into a dead end.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

from ..core import feeds
from .registry import register

log = logging.getLogger("mot")

DEFAULT = 5
MAX = 8
TTL = 300.0  # 5 min
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _host(url: str) -> str:
    try:
        return (urlsplit(url).netloc or "").replace("www.", "") or "web"
    except Exception:  # pragma: no cover - defensive
        return "web"


def _search(query: str, limit: int) -> list[dict[str, Any]]:
    """ddgs text search → cards. Raises whatever ddgs raises."""
    from ddgs import DDGS

    rows = DDGS(timeout=8).text(query, max_results=limit) or []
    now = time.strftime("%H:%M")
    return [
        {
            "title": str(row.get("title") or "").strip(),
            "source": _host(str(row.get("href") or "")),
            "when": now,
            "url": str(row.get("href") or "").strip(),
            "snippet": feeds.strip_html(str(row.get("body") or ""), 220),
        }
        for row in rows
        if row.get("title") and row.get("href")
    ][:limit]


def _fallback(query: str, limit: int) -> list[dict[str, Any]]:
    """Search the RSS pool when ddgs is down or rate limiting."""
    rows = feeds.search(query, limit=limit)
    return [
        {
            "title": row["title"],
            "source": row["source"] or feeds.label(row["url"]),
            "when": news_age(row["ts"]),
            "url": row["url"],
            "snippet": row["snippet"],
        }
        for row in rows
    ]


def news_age(ts: float) -> str:
    delta = max(0.0, time.time() - ts)
    if delta < 3600:
        return f"{max(1, int(delta // 60))}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


@register(
    "web_search",
    "Search the web for something Mot can't answer from a tool. "
    "Returns titles, sources, ages and links. Read-only.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "string", "description": "1-8 results, default 5"},
        },
        "required": ["query"],
    },
)
def web_search(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "message": "Search for what? Type a query first."}
    limit = _limit(args.get("max_results"))

    key = query.lower()
    hit = _CACHE.get(key)
    items: list[dict[str, Any]] = []
    if hit and time.time() - hit[0] <= TTL:
        items = hit[1]
    else:
        try:
            items = _search(query, limit)
        except Exception as exc:  # ddgs raises its own error types
            log.info("ddgs failed, falling back to feeds: %s", exc)
            try:
                items = _fallback(query, limit)
            except feeds.FeedError as fexc:
                return {
                    "ok": False,
                    "message": f"Web search is unavailable right now ({fexc.message})",
                }
            if not items:
                return {
                    "ok": False,
                    "message": "Web search is unavailable right now. Try again in a minute.",
                }
        _CACHE[key] = (time.time(), items)

    if not items:
        return {"ok": False, "message": f"No results for \u201c{query}\u201d."}
    return {
        "ok": True,
        "message": f"{len(items)} results for \u201c{query}\u201d.",
        "data": {"query": query, "items": items, "note": f"as of {time.strftime('%H:%M')}"},
    }


def _limit(value: Any) -> int:
    """Accepts a number or a numeric string from a JSON tool call."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT
    return max(1, min(MAX, n))
