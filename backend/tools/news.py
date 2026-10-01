"""get_news — headlines for a topic (gold, silver, crypto, markets). Read-only.

Feeds come from data/feeds.json (Settings > Feeds edits it). No model call:
this is the fast-path card and the first tool the LLM path reaches for.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from ..core import feeds
from .registry import register

MAX_ITEMS = 8


def _when(ts: float) -> str:
    """'3h' / '2d' — one short age string for the card."""
    delta = max(0.0, time.time() - ts)
    if delta < 3600:
        return f"{max(1, int(delta // 60))}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


def items_for(topic: str, limit: int = MAX_ITEMS) -> list[dict[str, Any]]:
    """Headlines shaped for the card: title, source, age, url, snippet."""
    rows = feeds.topic_items(topic, limit=limit)
    return [
        {
            "title": row["title"],
            "source": row["source"] or feeds.label(row["url"]),
            "when": _when(row["ts"]),
            "url": row["url"],
            "snippet": row["snippet"],
        }
        for row in rows
        if row.get("title") and row.get("url")
    ]


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
    try:
        items = items_for(topic)
    except feeds.FeedError as exc:
        return {
            "ok": False,
            "message": exc.message,
            "data": {
                "hint": "Add a feed in Settings → Feeds."
                if exc.code in ("empty", "no_topic")
                else "Check your connection and try again."
            },
        }
    if not items:
        return {
            "ok": False,
            "message": f"No fresh {topic} headlines right now.",
            "data": {"hint": "Check your connection and try again."},
        }
    newest = datetime.now().strftime("%H:%M")
    return {
        "ok": True,
        "message": f"{len(items)} {topic} headlines, newest first.",
        "data": {"topic": topic, "items": items, "note": f"as of {newest}"},
    }
