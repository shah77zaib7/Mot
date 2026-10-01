"""Phrases like "aj gold" or "market update today" that must never need a model.

The list lives in data/news_phrases.json (plain JSON, editable, no restart) so
anyone can add their own wording. A phrase matches when its words appear in the
message in order, and every message must also contain a word from `require_any`
— that is what stops a bare "aj" from firing a card.

topic: any feed topic ("gold", "forex", …) or "mixed" (gold + crypto + markets).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import config

log = logging.getLogger("mot")

PATH = config.DATA_DIR / "news_phrases.json"
MIXED = "mixed"

# A message needs one of these before any phrase can fire.
DEFAULT_REQUIRE = [
    "news", "update", "updates", "latest", "today", "price",
    "gold", "silver", "bitcoin", "btc", "crypto", "coin", "market", "markets",
    "forex", "xau", "dow", "nasdaq", "kal", "hua", "chal",
]

DEFAULT_PHRASES: list[dict[str, str]] = [
    {"text": "aj update", "topic": MIXED},
    {"text": "aaj update", "topic": MIXED},
    {"text": "aj news", "topic": MIXED},
    {"text": "aaj news", "topic": MIXED},
    {"text": "aj gold", "topic": "gold"},
    {"text": "aaj gold", "topic": "gold"},
    {"text": "aj silver", "topic": "silver"},
    {"text": "aj crypto", "topic": "crypto"},
    {"text": "aaj crypto", "topic": "crypto"},
    {"text": "aj bitcoin", "topic": "crypto"},
    {"text": "gold aur bitcoin", "topic": MIXED},
    {"text": "bitcoin aur gold", "topic": MIXED},
    {"text": "market update", "topic": "markets"},
    {"text": "aj market", "topic": "markets"},
    {"text": "aaj market", "topic": "markets"},
    {"text": "market kya hua", "topic": "markets"},
    {"text": "market kya chal raha hai", "topic": "markets"},
    {"text": "aj market kya hua", "topic": "markets"},
    {"text": "aj kya chal raha hai", "topic": MIXED},
    {"text": "aaj kya chal raha hai", "topic": MIXED},
    {"text": "aj kya hua", "topic": MIXED},
    {"text": "aaj ka haal", "topic": MIXED},
]

_WORDS = re.compile(r"[a-z0-9]+")
_cache: dict[str, Any] | None = None


def _words(text: str) -> list[str]:
    return _WORDS.findall(str(text or "").lower())


def load() -> dict[str, Any]:
    """The phrase file, written from the defaults the first time it is asked for."""
    global _cache
    if _cache is not None:
        return _cache
    raw: dict[str, Any] = {}
    try:
        loaded = json.loads(PATH.read_text(encoding="utf-8"))
        raw = loaded if isinstance(loaded, dict) else {}
    except FileNotFoundError:
        raw = {"require_any": list(DEFAULT_REQUIRE), "phrases": list(DEFAULT_PHRASES)}
        try:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            PATH.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            log.warning("can't write %s", PATH)
    except (OSError, json.JSONDecodeError):
        log.warning("news phrases unreadable, using the built-in list")
        raw = {}

    phrases = [
        {"text": str(e.get("text") or ""), "topic": str(e.get("topic") or "").strip().lower()}
        for e in (raw.get("phrases") or [])
        if isinstance(e, dict) and str(e.get("text") or "").strip() and str(e.get("topic") or "").strip()
    ]
    _cache = {
        "require_any": _words(" ".join(raw.get("require_any") or [])) or list(DEFAULT_REQUIRE),
        "phrases": phrases or list(DEFAULT_PHRASES),
    }
    return _cache


def save(data: dict[str, Any]) -> None:
    """Persist an edited list (kept simple: the whole file at once)."""
    global _cache
    _cache = None
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _in_order(phrase: list[str], words: list[str]) -> bool:
    """Every phrase word appears in the message, left to right (gaps allowed)."""
    position = 0
    for word in phrase:
        try:
            position = words.index(word, position) + 1
        except ValueError:
            return False
    return True


def match(text: str) -> str | None:
    """The topic a phrase claims for this message, or None."""
    words = _words(text)
    if not words:
        return None
    data = load()
    required = data.get("require_any") or []
    if required and not set(words) & set(required):
        return None  # a bare "aj" dies here
    for entry in data.get("phrases") or []:
        phrase = _words(entry.get("text"))
        if phrase and _in_order(phrase, words):
            topic = entry.get("topic")
            if topic:
                return topic
    return None


def reset() -> None:
    """Forget a cached read (tests, and Settings > Feeds edits)."""
    global _cache
    _cache = None
