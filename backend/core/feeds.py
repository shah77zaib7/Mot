"""RSS/Atom feeds for news topics — data/feeds.json, parallel fetch, caching.

`get_news` reads topics from here; Settings > Feeds edits this file through
the API. Fetches are parallel with an 8 s deadline, results are cached for
10 minutes (searches 5), HTML is stripped, snippets capped, and only the last
48 h is returned (if the window is empty we fall back to the newest items so
a quiet weekend never shows an empty card).
"""
from __future__ import annotations

import calendar
import concurrent.futures
import html
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, snapshot

log = logging.getLogger("mot")

FEEDS_PATH = config.DATA_DIR / "feeds.json"
TIMEOUT = 8.0
FEED_TTL = 600.0  # 10 min
SEARCH_TTL = 300.0  # 5 min
WINDOW = 48 * 3600  # 48 h
SNIPPET = 220  # chars kept per description

# Live-tested 2026-10-01 (see Memory.md). Dead feeds were dropped, not kept.
DEFAULTS: dict[str, list[str]] = {
    "gold": [
        "https://news.google.com/rss/search?q=gold+price&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=gold&hl=en-US&gl=US&ceid=US:en",
    ],
    "silver": [
        "https://news.google.com/rss/search?q=silver+price&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=silver+price+OR+silver+market&hl=en-US&gl=US&ceid=US:en",
    ],
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
    ],
    "markets": [
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "https://seekingalpha.com/market_currents.xml",
        "https://www.investing.com/rss/news_1.rss",
    ],
}

# Loose spellings the fast path and the tools accept → a topic key above.
ALIASES: dict[str, str] = {
    "xau": "gold",
    "gold price": "gold",
    "bullion": "gold",
    "xag": "silver",
    "silver price": "silver",
    "btc": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "eth": "crypto",
    "coins": "crypto",
    "cryptocurrency": "crypto",
    "crypto market": "crypto",
    "stock": "markets",
    "stocks": "markets",
    "stock market": "markets",
    "shares": "markets",
    "equities": "markets",
    "forex": "markets",
    "wall street": "markets",
    "market": "markets",
}

# Words people add before a topic that say nothing about it.
FILLER = {
    "the", "a", "an", "latest", "todays", "today", "breaking", "current",
    "recent", "top", "some", "my", "find", "search", "for", "me", "show",
    "give", "get", "tell", "read", "list", "fetch", "please", "news",
}

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class FeedError(Exception):
    """A feed problem worth showing, with a short code the UI can switch on."""

    def __init__(self, message: str, code: str = "feed") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# --- storage ----------------------------------------------------------------

def _ensure_file() -> None:
    if FEEDS_PATH.exists():
        return
    try:
        FEEDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        save(DEFAULTS)
    except OSError:  # unwritable location: read() then falls back to DEFAULTS
        log.warning("can't create %s", FEEDS_PATH)


def load() -> dict[str, list[str]]:
    """{topic: [url, …]}; a missing or broken file falls back to DEFAULTS."""
    _ensure_file()
    try:
        raw = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("feeds.json unreadable; using defaults")
        raw = DEFAULTS
    feeds: dict[str, list[str]] = {}
    if isinstance(raw, dict):
        for topic, urls in raw.items():
            if not isinstance(urls, list):
                continue
            clean = [str(u).strip() for u in urls if isinstance(u, (str, int, float)) and str(u).strip()]
            if clean:
                feeds[str(topic).strip().lower() or str(topic)] = clean
    if not feeds:
        return {k: list(v) for k, v in DEFAULTS.items()}
    return feeds


def save(feeds: dict[str, list[str]]) -> None:
    """Persist the whole structure (Settings > Feeds) and drop the cache."""
    FEEDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        str(topic): [str(u).strip() for u in (urls or []) if str(u).strip()]
        for topic, urls in (feeds or {}).items()
        if str(topic).strip()
    }
    FEEDS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    clear_cache()  # a live edit must show up on the very next request


def topics() -> list[str]:
    return sorted(load())


def topic_key(text: str) -> str | None:
    """'XAU news' → 'gold'; an unknown word returns None (LLM path handles it)."""
    key = " ".join(str(text or "").lower().split()).strip(" ?!.,:;'\"")
    if not key:
        return None
    known = load()
    if key in known:
        return key  # a topic the user really saved ("forex") beats an alias
    key = ALIASES.get(key, key)
    if key in known:
        return key
    for name in known:
        if key == name or key.startswith(f"{name} ") or key.endswith(f" {name}"):
            return name
    return None


# --- fetching ---------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text: str, limit: int = SNIPPET) -> str:
    """Tags out, entities unescaped, whitespace folded, length capped."""
    clean = html.unescape(_TAG.sub(" ", str(text or "")))
    clean = _WS.sub(" ", clean).strip()
    return clean[: limit - 1] + "…" if len(clean) > limit else clean


def _entry_time(entry: Any) -> float:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return float(calendar.timegm(parsed))
        except (TypeError, ValueError, OverflowError):
            pass
    return time.time()


def _entry_source(entry: Any, feed_title: str) -> str:
    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return strip_html(str(source["title"]), 60)
    return strip_html(feed_title, 60)


def fetch_feed(url: str, timeout: float = TIMEOUT) -> tuple[str, list[dict[str, Any]]]:
    """One feed → (feed title, items). Raises FeedError with a friendly code."""
    import feedparser  # local: keeps import cheap for runs that never read news

    request = urllib.request.Request(url, headers={"User-Agent": "Mot/1.0 (news reader)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4_000_000)
    except TimeoutError as exc:
        raise FeedError(f"{label(url)} timed out.", "timeout") from exc
    except urllib.error.HTTPError as exc:
        raise FeedError(f"{label(url)} answered HTTP {exc.code}.", "http") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise FeedError(f"Couldn't reach {label(url)}.", "unreachable") from exc

    parsed = feedparser.parse(raw)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise FeedError(f"{label(url)} isn't a feed Mot can read.", "parse")

    feed_title = ""
    if isinstance(getattr(parsed, "feed", None), dict):
        feed_title = str(parsed.feed.get("title") or "")
    return feed_title, [
        {
            "title": strip_html(entry.get("title") or "", 180),
            "url": str(entry.get("link") or "").strip(),
            "source": _entry_source(entry, feed_title or label(url)),
            "ts": int(_entry_time(entry)),
            "snippet": strip_html(entry.get("summary") or entry.get("description") or ""),
        }
        for entry in parsed.entries[:40]
        if entry.get("title") and entry.get("link")
    ]


def label(url: str) -> str:
    """Host name, for messages: 'Couldn't reach cointelegraph.com.'"""
    try:
        host = urllib.parse.urlsplit(url).netloc
    except Exception:
        host = ""
    return (host or url).replace("www.", "")


def _fetch_map(urls: list[str], timeout: float = TIMEOUT) -> dict[str, tuple[list[dict[str, Any]] | None, str]]:
    """Fetch every feed at once: {url: (rows, "")} or {url: (None, reason)}.

    One dead feed never kills the others — every URL gets an answer here.
    """
    report: dict[str, tuple[list[dict[str, Any]] | None, str]] = {}
    if not urls:
        return report
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        futures = {pool.submit(fetch_feed, url): url for url in urls}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                url = futures[future]
                try:
                    _, rows = future.result()
                    report[url] = (rows, "")
                except FeedError as exc:
                    report[url] = (None, exc.message)
                except Exception as exc:  # pragma: no cover - defensive
                    report[url] = (None, str(exc))
        except concurrent.futures.TimeoutError:
            pending = [u for f, u in futures.items() if u not in report]
            for url in pending:
                report[url] = (None, f"took longer than {int(timeout)} s.")
    return report


def _parallel(urls: list[str]) -> list[dict[str, Any]]:
    """Fetch every feed at once, give up after TIMEOUT, keep whatever landed."""
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not urls:
        return items
    for rows, reason in _fetch_map(urls).values():
        if rows is None:
            errors.append(reason)
        else:
            items.extend(rows)
    if errors and not items:
        raise FeedError(errors[0], "all_failed")
    if errors:
        log.info("feeds partial: %s", "; ".join(errors[:3]))
    return items


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = item.get("url") or item.get("title", "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda i: i.get("ts", 0), reverse=True)
    return out


def _fresh(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    now = time.time()
    window = [i for i in items if now - i.get("ts", now) <= WINDOW]
    # a quiet weekend still shows the newest headlines rather than nothing
    return (window or items)[:limit]


def _cached(key: str, ttl: float, build: Any) -> list[dict[str, Any]]:
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] <= ttl:
            return hit[1]
    value = build()
    with _LOCK:
        _CACHE[key] = (time.time(), value)
    return value


# --- public helpers ---------------------------------------------------------

def topic_items(topic: str, limit: int = 12) -> list[dict[str, Any]]:
    """News for one topic: parallel fetch, 10 min cache, 48 h window, deduped."""
    key = topic_key(topic)
    if key is None:
        raise FeedError(f"Mot has no feeds for \u201c{topic}\u201d yet.", "no_topic")
    urls = load().get(key, [])
    if not urls:
        raise FeedError(f"No feeds saved for {key} yet.", "empty")

    def build() -> list[dict[str, Any]]:
        return _fresh(_dedupe(_parallel(urls)), limit)

    return _cached(f"topic:{key}", FEED_TTL, build)


# Topics that make up the ambiguous "mixed" card (see core/phrases.py).
MIXED_TOPICS = ("gold", "crypto", "markets")
SNAPSHOT_ITEMS = 40  # headlines kept per topic on disk


def read_topic(topic: str, limit: int = 12) -> dict[str, Any]:
    """News for one topic *without waiting on the network* when we already have it.

    Order: hot cache → saved snapshot → one bounded live read (only when the
    snapshot is older than 3 h) → the snapshot again, marked offline. Returns
    {items, updated, offline, failed} so the card can be labelled honestly.
    """
    key = topic_key(topic)
    if key is None:
        raise FeedError(f"Mot has no feeds for \u201c{topic}\u201d yet.", "no_topic")
    if not load().get(key, []):
        raise FeedError(f"No feeds saved for {key} yet.", "empty")

    hot = _CACHE.get(f"topic:{key}")
    if hot and time.time() - hot[0] <= FEED_TTL:
        return {
            "items": hot[1][:limit], "updated": hot[0],
            "offline": False, "failed": snapshot.failed_count(),
        }

    saved = snapshot.items(key, limit)
    when = snapshot.fetched_at()
    if saved and not snapshot.is_stale():
        with _LOCK:
            _CACHE[f"topic:{key}"] = (when or time.time(), snapshot.items(key, SNAPSHOT_ITEMS))
        return {
            "items": saved, "updated": when,
            "offline": False, "failed": snapshot.failed_count(),
        }

    try:
        rows = topic_items(key, limit)  # live + 10 min cache, 8 s deadline
    except FeedError:
        if saved:  # offline: headlines we already had, clearly labelled
            return {
                "items": saved, "updated": when,
                "offline": True, "failed": snapshot.failed_count(),
            }
        raise
    return {
        "items": rows, "updated": time.time(),
        "offline": False, "failed": snapshot.failed_count(),
    }


def mixed_items(limit: int = 12) -> list[dict[str, Any]]:
    """The ambiguous card: gold + crypto + markets together, newest first."""
    pool: list[dict[str, Any]] = []
    errors: list[str] = []
    for name in MIXED_TOPICS:
        try:
            pool.extend(read_topic(name, limit * 2)["items"])
        except FeedError as exc:
            errors.append(exc.message)
    if not pool and errors:
        raise FeedError(errors[0], "all_failed")
    return _dedupe(pool)[:limit]


def refresh_all() -> dict[str, Any]:
    """The background job: fetch every feed of every topic, save, and report.

    One dead feed never fails the run — its reason is logged per source and
    counted, everything else still lands in data/market_ingest/latest.json.
    """
    topics = load()
    url_topic = {url: name for name, urls in topics.items() for url in urls}
    report = _fetch_map(list(url_topic))

    by_topic: dict[str, list[dict[str, Any]]] = {}
    for name in topics:
        pool: list[dict[str, Any]] = []
        for url, target in url_topic.items():
            if target != name:
                continue
            rows, _reason = report.get(url, (None, "no answer"))
            pool.extend(rows or [])
        by_topic[name] = _fresh(_dedupe(pool), SNAPSHOT_ITEMS)

    summary = snapshot.write(by_topic, {url: r[1] for url, r in report.items()})
    stamp = summary.get("fetched_at") or time.time()
    with _LOCK:
        for name, rows in by_topic.items():
            _CACHE[f"topic:{name}"] = (stamp, rows)

    for url, (rows, reason) in report.items():
        log.info("ingest %s: %s", label(url), reason or f"{len(rows or [])} items")
    log.info(
        "ingest done: %s topics, %s sources, %s failed",
        len(by_topic), summary["sources"], summary["failed"],
    )
    return {**summary, "topics": {k: len(v) for k, v in by_topic.items()}}


def all_items(limit: int = 40) -> list[dict[str, Any]]:
    """Every feed, deduped — the pool web_search falls back to."""
    pool: list[dict[str, Any]] = []
    errors: list[str] = []
    for urls in load().values():
        try:
            pool.extend(_parallel(urls))
        except FeedError as exc:
            errors.append(exc.message)
    if not pool and errors:
        raise FeedError(errors[0], "all_failed")
    return _dedupe(pool)[: max(limit, 80)]


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Plain keyword search across every feed (web_search's fallback)."""
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    if not words:
        return []

    def build() -> list[dict[str, Any]]:
        hits = [
            item
            for item in all_items()
            if words & set(re.findall(r"[a-z0-9]+", (item.get("title", "") + " " + item.get("snippet", "")).lower()))
        ]
        return hits[:limit]

    return _cached(f"search:{query.lower().strip()}", SEARCH_TTL, build)


def test_feed(url: str) -> dict[str, Any]:
    """Settings > Feeds → 'Test': fetch one URL and report what came back."""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "message": "That doesn't look like an http(s) URL.", "count": 0}
    try:
        title, rows = fetch_feed(url, timeout=TIMEOUT)
    except FeedError as exc:
        return {"ok": False, "message": exc.message, "count": 0}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "message": f"Couldn't read that feed: {exc}", "count": 0}
    if not rows:
        return {"ok": False, "message": f"{label(url)} answered, but had no items.", "count": 0}
    newest = datetime.fromtimestamp(rows[0]["ts"], tz=timezone.utc).astimezone()
    return {
        "ok": True,
        "message": f"✓ {title or label(url)} — {len(rows)} items, newest {newest:%b %d, %H:%M}",
        "count": len(rows),
    }


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
