"""get_news — headlines for a topic (gold, silver, crypto, markets). Read-only.

Reads the cache or the saved snapshot first so a card appears instantly, goes to
the network only when the snapshot is older than 3 h, and if everything fails it
tries a plain web search before admitting defeat with a Retry card. No model
call: this is the fast-path card and the first tool the LLM path reaches for.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from ..core import feeds, snapshot
from .registry import register

MAX_ITEMS = 8
MIXED_ITEMS = 12
MIXED = "mixed"

# What the last successful read was, for the card's "Updated / offline / failed"
# line. items_for() fills it; get_news() reads it straight after.
_META: dict[str, Any] = {"updated": None, "offline": False, "failed": 0}


def _when(ts: float) -> str:
    """'3h' / '2d' — one short age string for the card."""
    delta = max(0.0, time.time() - ts)
    if delta < 3600:
        return f"{max(1, int(delta // 60))}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


def _shape(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Headlines shaped for the card: title, source, age, url, snippet."""
    return [
        {
            "title": row["title"],
            "source": row["source"] or feeds.label(row["url"]),
            "when": row.get("when") or _when(row.get("ts") or 0),
            "url": row["url"],
            "snippet": row.get("snippet") or "",
        }
        for row in rows
        if row.get("title") and row.get("url")
    ]


def _read(topic: str, limit: int) -> dict[str, Any]:
    """Cache/snapshot first, one bounded network read only when needed."""
    if topic.strip().lower() == MIXED:
        rows = feeds.mixed_items(limit)
        return {
            "items": rows, "updated": snapshot.fetched_at(),
            "offline": False, "failed": snapshot.failed_count(),
        }
    return feeds.read_topic(topic, limit)


def _web_fallback(topic: str) -> list[dict[str, Any]]:
    """Last resort when no feed and no snapshot answer: a plain web search."""
    from . import websearch  # imported late: websearch imports feeds too

    try:
        result = websearch.web_search({"query": f"{topic} news", "max_results": MAX_ITEMS})
    except Exception:  # pragma: no cover - defensive
        return []
    if not result.get("ok"):
        return []
    return list(result.get("data", {}).get("items") or [])


def items_for(topic: str, limit: int = MAX_ITEMS) -> list[dict[str, Any]]:
    """Headlines shaped for the card: title, source, age, url, snippet."""
    global _META
    read = _read(topic, limit)
    _META = {
        "updated": read.get("updated"),
        "offline": bool(read.get("offline")),
        "failed": int(read.get("failed") or 0),
    }
    return _shape(read["items"])


@register(
    "get_news",
    "Latest news headlines for a topic (gold, silver, crypto, markets). "
    "Returns titles, sources, ages and links. Read-only.",
    {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
)
def get_news(args: dict[str, Any]) -> dict[str, Any]:
    topic = str(args.get("topic") or "").strip()
    if not topic:
        return {"ok": False, "message": "Which topic? Try gold, silver, crypto or markets."}

    global _META
    _META = {"updated": None, "offline": False, "failed": 0}
    items: list[dict[str, Any]] = []
    try:
        items = items_for(topic, MIXED_ITEMS if topic.lower() == MIXED else MAX_ITEMS)
    except feeds.FeedError as exc:
        if exc.code in ("empty", "no_topic"):
            return {
                "ok": False,
                "message": exc.message,
                "data": {"hint": "Add a feed in Settings → Feeds."},
            }
        # unreachable feeds: say so plainly instead of falling through to the model

    if not items:
        items = _shape(_web_fallback(topic))  # feeds down → a plain web search

    if not items:
        return {
            "ok": False,
            "message": "Couldn't reach the news sources.",
            "data": {
                "hint": "Retry, or check the list in Settings → Feeds.",
                "retry": True,
                "failed": snapshot.failed_count(),
            },
        }

    updated = _META.get("updated")
    stamp = datetime.fromtimestamp(updated).strftime("%H:%M") if updated else time.strftime("%H:%M")
    note = f"as of {stamp} (offline)" if _META.get("offline") else f"as of {stamp}"
    subject = "top gold, crypto and market" if topic.lower() == MIXED else topic
    return {
        "ok": True,
        "message": f"{len(items)} {subject} headlines, newest first.",
        "data": {
            "topic": topic,
            "items": items,
            "note": note,
            "updated": stamp,
            "offline": bool(_META.get("offline")),
            "failed": int(_META.get("failed") or 0),
            "sources": snapshot.total_count(),
        },
    }
