"""web_search — ddgs results, 5-min cache, and the feed fallback when it fails."""
from __future__ import annotations

import pytest

from backend.core import feeds
from backend.tools import registry
from backend.tools import websearch as ws

ROWS = [
    {"title": "Gold climbs past $2,600", "url": "https://www.kitco.com/news/1",
     "source": "kitco.com", "when": "14:32",
     "snippet": "Gold & silver rose on Tuesday."},
    {"title": "Dollar softens", "url": "https://www.reuters.com/markets/2",
     "source": "reuters.com", "when": "14:32", "snippet": "The dollar index fell."},
]


@pytest.fixture
def clean(monkeypatch, tmp_path):
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    ws._CACHE.clear()
    feeds.clear_cache()
    yield ws
    ws._CACHE.clear()
    feeds.clear_cache()


@pytest.fixture
def ddgs_ok(monkeypatch, clean):
    calls: list[tuple[str, int]] = []

    def fake_search(query: str, limit: int):
        calls.append((query, limit))
        return ROWS[:limit]

    monkeypatch.setattr(ws, "_search", fake_search)
    return calls


def test_web_search_returns_a_card(ddgs_ok):
    result = registry.call("web_search", {"query": "gold price"})

    assert result["ok"] is True
    assert len(result["data"]["items"]) == 2
    assert result["data"]["items"][0]["url"].startswith("https://")
    assert result["data"]["note"].startswith("as of ")
    assert ddgs_ok == [("gold price", 5)]  # default of 5


def test_max_results_is_read_from_text(ddgs_ok):
    registry.call("web_search", {"query": "gold", "max_results": "8"})

    assert ddgs_ok[-1] == ("gold", 8)


def test_results_are_cached_for_five_minutes(ddgs_ok):
    registry.call("web_search", {"query": "gold"})
    registry.call("web_search", {"query": "gold"})

    assert len(ddgs_ok) == 1


def test_a_empty_query_is_refused(clean):
    result = registry.call("web_search", {"query": "   "})

    assert result["ok"] is False and "query" in result["message"].lower()


def test_when_ddgs_fails_we_search_the_feeds_instead(monkeypatch, clean):
    def boom(query, limit):  # noqa: ARG001
        raise RuntimeError("rate limited")

    monkeypatch.setattr(ws, "_search", boom)
    monkeypatch.setattr(feeds, "search", lambda q, limit=5: [
        {"title": "Gold rally continues", "url": "https://k/1", "source": "Kitco",
         "ts": 0, "snippet": "gold"},
    ])
    monkeypatch.setattr(ws, "news_age", lambda ts: "2h")  # noqa: ARG005

    result = registry.call("web_search", {"query": "gold"})

    assert result["ok"] is True
    assert result["data"]["items"][0]["source"] == "Kitco"


def test_when_both_fail_the_message_is_friendly(monkeypatch, clean):
    monkeypatch.setattr(ws, "_search", lambda q, n: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(feeds, "search", lambda q, limit=5: [])  # noqa: ARG005

    result = registry.call("web_search", {"query": "gold"})

    assert result["ok"] is False
    assert "unavailable" in result["message"].lower()
    assert "Traceback" not in result["message"]


def test_no_results_says_so(monkeypatch, clean):
    monkeypatch.setattr(ws, "_search", lambda q, n: [])

    result = registry.call("web_search", {"query": "zzzz nothing"})

    assert result["ok"] is False and "No results" in result["message"]
