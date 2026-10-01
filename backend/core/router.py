"""Fast path — turn common commands into steps with no model call at all.

parse("open youtube and search lo-fi") -> [open_url, search_in_browser]
parse("why is gold moving")            -> None  (normal chat, Phase 3 may add tools)
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from . import apps, routines
from .feeds import FILLER, topic_key
from ..tools.search import ALIASES, ENGINES, engine_key

# Short names -> URLs for "open X".
SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "gmail": "https://mail.google.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "linkedin": "https://www.linkedin.com",
    "chatgpt": "https://chatgpt.com",
    "spotify": "https://open.spotify.com",
    "tradingview": "https://www.tradingview.com",
    "wikipedia": "https://www.wikipedia.org",
    "whatsapp web": "https://web.whatsapp.com",
    "discord": "https://discord.com/app",
    "stack overflow": "https://stackoverflow.com",
    "ollama": "https://ollama.com",
}

_SPLIT = re.compile(r"\s+(?:and|then)\s+|;", re.IGNORECASE)
_URL_LIKE = re.compile(
    r"^(?:https?://|www\.)[^\s]+$|^[a-z0-9-]+(\.[a-z0-9-]{2,})+([/?#].*)?$"
    r"|^[a-z0-9-]+(:\d+)(/.*)?$",
    re.IGNORECASE,
)
_OPEN = re.compile(r"^(?:go to|open|visit|head to|navigate to)\s+(.+)$", re.IGNORECASE)
_INSTALL = re.compile(r"^(?:install|download)\s+(.+)$", re.IGNORECASE)
_PLAY_ON = re.compile(r"^(?:play|put on)\s+(.+?)\s+on\s+(?:youtube|yt)$", re.IGNORECASE)
_SEARCH_ON = re.compile(r"^(?:search for|search|google|look up|find)\s+(.+?)\s+on\s+(.+)$", re.IGNORECASE)
_SEARCH_SITE_FOR = re.compile(r"^(?:search|find)\s+([a-z0-9 ]+?)\s+for\s+(.+)$", re.IGNORECASE)
_SEARCH = re.compile(r"^(?:search for|search|google|look up|find)\s+(.+)$", re.IGNORECASE)
_NEWS = re.compile(r"^(?:the\s+)?(.+?)\s+news$", re.IGNORECASE)
_NEWS_ABOUT = re.compile(r"^(?:the\s+)?news\s+(?:about|on|for)\s+(.+)$", re.IGNORECASE)
_RUN = re.compile(r"^(?:run|start|do|begin|execute|play)\s+(?:my\s+|the\s+)?(.+)$", re.IGNORECASE)


def _clean(text: str) -> str:
    s = " ".join((text or "").split())
    s = re.sub(r"^(?:hey |hi |ok |okay )?mot[,\s]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:please|pls|could you|can you|would you|kindly)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(?:please|pls|thanks|thank you)$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(?:now|for me|today|real quick)$", "", s, flags=re.IGNORECASE)
    return s.strip(" .!?;:,\t")


def _segments(text: str) -> list[str]:
    return [p.strip(" .,!?") for p in _SPLIT.split(_clean(text)) if p and p.strip(" .,!?:")]


def _url_like(arg: str) -> bool:
    return bool(_URL_LIKE.match(arg.strip()))


def _site_url(word: str) -> str | None:
    key = " ".join(word.lower().split())
    return SITES.get(key)


def _known_engine(word: str) -> str | None:
    key = " ".join(word.lower().split())
    key = ALIASES.get(key, key)
    return key if key in ENGINES else None


# Conversational "good news!" must not become a search.
_NEWS_NO = {"good", "bad", "great", "wonderful", "amazing", "funny", "sad",
            "happy", "weird", "nice", "terrible", "horrible", "serious"}
# A sentence that only happens to end in "news" is not a news request.
_NEWS_STOP = {
    "i", "you", "we", "he", "she", "it", "they", "me", "him", "her", "us",
    "them", "have", "has", "had", "got", "there", "here", "is", "are", "was",
    "were", "be", "been", "do", "does", "did", "can", "could", "will",
    "would", "should", "may", "might", "must", "your", "our", "their",
    "not", "just", "only", "real", "very", "with", "and", "or", "but",
    "if", "up", "out", "on", "in", "at", "to", "of", "from", "that",
    "this", "what", "when", "where", "who", "how", "why", "which",
}
_NEWS_WORD = re.compile(r"^[a-z][a-z0-9 -]{1,29}$", re.IGNORECASE)


def _news_topic(text: str) -> str | None:
    """'<topic> news' -> the topic, or None when this isn't a news request."""
    m = _NEWS.match(text) or _NEWS_ABOUT.match(text)
    if not m:
        return None
    words = m.group(1).split()
    while words and words[0].lower() in FILLER:
        words.pop(0)
    while words and words[-1].lower() in FILLER:
        words.pop()
    topic = " ".join(words)
    if not topic or len(words) > 4:
        return None
    if not _NEWS_WORD.match(topic) or topic.lower() in _NEWS_NO:
        return None
    if any(w.lower() in _NEWS_STOP for w in words):
        return None
    return topic


def _news_step(low: str, orig: str) -> list[dict[str, Any]] | None:
    """News card, no model: known topic -> feeds, anything else -> web_search."""
    topic = _news_topic(low)
    if topic is None:
        return None
    if topic_key(topic) is not None:
        return [{"action": "get_news", "topic": topic}]
    return [{"action": "web_search", "query": f"{topic} news"}]


def _segment(orig: str, site: str | None) -> tuple[list[dict[str, Any]], str | None] | None:
    """Parse one segment. Returns (steps, inherited site) or None."""
    low = orig.lower().strip()
    if not low:
        return None

    m = _INSTALL.match(low)
    if m:
        return [{"action": "install_app", "name": orig[m.start(1):].strip()}], site

    m = _PLAY_ON.match(low)  # "play dilbar on youtube" -> one YouTube tab
    if m:
        query = orig[m.start(1):m.end(1)].strip()
        return [{"action": "play_youtube", "query": query}], "youtube"

    m = _RUN.match(low)
    if m:
        target = m.group(1).strip()
        hit = routines.get(target)
        if hit is not None:
            return [{"action": "run_routine", "name": hit["name"]}], site
        if site == "youtube" and low[: m.start(1)].strip().startswith("play"):
            # "open youtube then play X" -> the video, not the bare homepage
            return [{"action": "play_youtube", "query": orig[m.start(1):].strip()}], site
        # "start chrome" / "run youtube" behave like "open …"
        arg = orig[m.start(1):].strip()
        url = _site_url(arg)
        if url:
            key = " ".join(arg.lower().split())
            return [{"action": "open_url", "url": url, "site": key}], key
        if arg and apps.match(arg) is not None:
            return [{"action": "open_app", "name": arg}], site
    routine_hit = routines.get(low)
    if routine_hit is not None:
        return [{"action": "run_routine", "name": routine_hit["name"]}], site

    m = _SEARCH_ON.match(low)
    if m:
        query = orig[m.start(1):m.end(1)].strip()
        return (
            [{"action": "search_in_browser",
              "site": engine_key(orig[m.start(2):m.end(2)]), "query": query}],
            engine_key(orig[m.start(2):m.end(2)]),
        )

    m = _SEARCH_SITE_FOR.match(low)
    if m and _known_engine(m.group(1)) is not None:
        key = _known_engine(m.group(1)) or "google"
        return (
            [{"action": "search_in_browser", "site": key,
              "query": orig[m.start(2):m.end(2)].strip()}],
            key,
        )

    news = _news_step(low, orig)
    if news is not None:
        return news, None

    m = _SEARCH.match(low)
    if m:
        key = site or "google"
        return (
            [{"action": "search_in_browser", "site": key,
              "query": orig[m.start(1):].strip()}],
            key,
        )

    m = _OPEN.match(low)
    if m:
        arg = orig[m.start(1):].strip()
        if _url_like(arg):
            return [{"action": "open_url", "url": arg}], site
        url = _site_url(arg)
        if url:
            key = " ".join(arg.lower().split())
            return [{"action": "open_url", "url": url, "site": key}], key
        # Not a site and not an installed app: hand the segment to the model
        # instead of a failure card ("open the gold chart on tradingview").
        if arg and apps.match(arg) is not None:
            return [{"action": "open_app", "name": arg}], site
        return None

    if _url_like(low):
        return [{"action": "open_url", "url": orig.strip()}], site
    bare = orig.strip()  # "open chrome then whatsapp" -> bare app / site name
    url = _site_url(bare)
    if url:
        key = " ".join(bare.lower().split())
        return [{"action": "open_url", "url": url, "site": key}], key
    if len(bare.split()) <= 3 and apps.claims(bare):
        return [{"action": "open_app", "name": bare}], site
    return None


def step_host(step: dict[str, Any]) -> str | None:
    """The exact host a step will open (None when the step opens nothing).

    Hosts, not domains: a search that fell back to Google must never cover
    "open gmail" (mail.google.com is not google.com).
    """
    action = step.get("action")
    if action == "open_url":
        return _host(str(step.get("url") or ""))
    if action == "search_in_browser":
        key = engine_key(str(step.get("site") or ""))
        if key == "maps":
            return "maps.google.com"
        return _host(ENGINES[key]) if key in ENGINES else None
    if action == "play_youtube":
        return "youtube.com"
    return None


def _host(url: str) -> str:
    if url and "://" not in url:
        url = "https://" + url.lstrip("/")
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def drop_covered_opens(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One tab per site: drop a plain "open X" that a later step opens anyway.

    "open youtube and search lo-fi" is one search results page, not two tabs.
    """
    kept: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if step.get("action") == "open_url":
            host = step_host(step)
            later = [step_host(other) for other in steps[index + 1:]]
            if host and host in later:
                continue
        kept.append(step)
    return kept


def parse_parts(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Split a message into (fast-path steps, segments the rules don't know).

    The fast path handles every segment it recognises; whatever is left is
    handed to the LLM router (Phase 3).
    """
    steps: list[dict[str, Any]] = []
    rest: list[str] = []
    site: str | None = None
    for part in _segments(text):
        parsed = _segment(part, site)
        if parsed is None:
            rest.append(part)
            continue
        part_steps, site = parsed
        steps.extend(part_steps)
    return drop_covered_opens(steps), rest


def parse(text: str) -> list[dict[str, Any]] | None:
    """Steps for a command, or None when it isn't a fast-path command."""
    steps, rest = parse_parts(text)
    return steps if steps and not rest else None
