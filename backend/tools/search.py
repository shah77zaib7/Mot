"""search_in_browser — build a search URL and open it (no API, no key)."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from ..core import apps
from . import launch
from .registry import register
from .open_url import normalize_url

ENGINES: dict[str, str] = {
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "maps": "https://www.google.com/maps/search/{q}",
}

ALIASES: dict[str, str] = {
    "yt": "youtube",
    "ddg": "duckduckgo",
    "duck": "duckduckgo",
    "google maps": "maps",
    "googlemap": "maps",
    "map": "maps",
}

DISPLAY = {
    "google": "Google",
    "bing": "Bing",
    "duckduckgo": "DuckDuckGo",
    "youtube": "YouTube",
    "maps": "Google Maps",
}


def engine_key(site: str) -> str:
    """Normalize a site name to an engine key; unknown sites fall back to Google."""
    key = " ".join((site or "").lower().split())
    key = ALIASES.get(key, key)
    return key if key in ENGINES else "google"


def search_url(site: str, query: str) -> str:
    return ENGINES[engine_key(site)].format(q=quote_plus((query or "").strip()))


@register(
    "search_in_browser",
    "Search the web for something (YouTube, Google, Bing, DuckDuckGo, Maps).",
    {
        "type": "object",
        "properties": {
            "site": {"type": "string", "description": "youtube, google, bing, duckduckgo, maps"},
            "query": {"type": "string"},
        },
        "required": ["query"],
    },
)
def search_in_browser(args: dict[str, Any]) -> dict[str, Any]:
    query = (args.get("query") or "").strip()
    if not query:
        return {"ok": False, "message": "There was nothing to search for.", "data": {}}
    site = args.get("site") or "google"
    key = engine_key(site)
    url = search_url(site, query)
    launch.open_url(normalize_url(url), browser=apps.browser())
    return {
        "ok": True,
        "message": f"Searched {DISPLAY.get(key, key)} for \u201c{query}\u201d.",
        "data": {"url": url, "engine": key, "label": DISPLAY.get(key, key), "query": query},
    }
