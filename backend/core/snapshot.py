"""Saved headlines — data/market_ingest/latest.json.

Headlines and links only, never article text (requirement: keep it small and
non-sensitive). The background refresh (core.ingest) rewrites this every two
hours; get_news reads it *before* touching the network, so news is instant on a
slow connection and still shows something when offline.

Item shape on disk: {title, url, source, published_at, fetched_at, topic}.
Read back in the live shape: {title, url, source, ts, snippet}.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from . import config

DIR = config.DATA_DIR / "market_ingest"
PATH = DIR / "latest.json"
STALE_AFTER = 3 * 3600  # older than 3 h and the next read tries the network once

_LOCK = threading.Lock()


def _row(item: dict[str, Any], topic: str, fetched: float) -> dict[str, Any]:
    """Headline + link + source + the two timestamps — nothing else."""
    return {
        "title": item.get("title") or "",
        "url": item.get("url") or "",
        "source": item.get("source") or "",
        "published_at": int(item.get("ts") or item.get("published_at") or 0),
        "fetched_at": int(fetched),
        "topic": topic,
    }


def write(topics: dict[str, list[dict[str, Any]]], sources: dict[str, str]) -> dict[str, Any]:
    """Save every topic plus per-source status (url -> "" when it was fine)."""
    fetched = time.time()
    payload = {
        "fetched_at": fetched,
        "topics": {
            topic: [_row(item, topic, fetched) for item in items]
            for topic, items in topics.items()
        },
        "sources": {str(url): reason for url, reason in sources.items()},
    }
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:  # read-only folder: the caller still has its in-memory result
        return summary(payload)
    return summary(payload)


def read() -> dict[str, Any]:
    """The whole file, or {} when it is missing/broken."""
    with _LOCK:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return data if isinstance(data, dict) else {}


def fetched_at() -> float | None:
    value = read().get("fetched_at")
    return float(value) if isinstance(value, (int, float)) else None


def age() -> float | None:
    """Seconds since the last refresh, or None when there is no snapshot."""
    stamp = fetched_at()
    return None if stamp is None else max(0.0, time.time() - stamp)


def is_stale() -> bool:
    """True when the next read should make one bounded attempt at the network."""
    seconds = age()
    return seconds is None or seconds > STALE_AFTER


def items(topic: str, limit: int = 12) -> list[dict[str, Any]]:
    """Saved headlines for one topic, in the same shape the card expects."""
    rows = read().get("topics")
    if not isinstance(rows, dict):
        return []
    out: list[dict[str, Any]] = []
    for item in rows.get(topic) or []:
        if isinstance(item, dict) and item.get("title") and item.get("url"):
            out.append(
                {
                    "title": item["title"],
                    "url": item["url"],
                    "source": item.get("source") or "",
                    "ts": int(item.get("published_at") or 0),
                    "snippet": "",
                }
            )
    return out[:limit]


def sources() -> dict[str, str]:
    raw = read().get("sources")
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def failed_count() -> int:
    return sum(1 for reason in sources().values() if reason)


def total_count() -> int:
    return len(sources())


def summary(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the card and the Feeds tab show: counts plus the refresh time."""
    data = data if data is not None else read()
    raw = data.get("sources") or {}
    fetched = data.get("fetched_at")
    return {
        "fetched_at": float(fetched) if isinstance(fetched, (int, float)) else None,
        "sources": len(raw),
        "failed": sum(1 for reason in raw.values() if reason),
    }
