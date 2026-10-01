"""get_news + the '<topic> news' fast path — a headlines card with no model."""
from __future__ import annotations

import time

import pytest

from backend.core import feeds, router
from backend.tools import registry


def _item(title: str, i: int = 0) -> dict:
    return {
        "title": title,
        "source": "Kitco",
        "when": "2h",
        "url": f"https://kitco.com/{i}",
        "snippet": "Gold and silver moved.",
    }


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    feeds.clear_cache()
    yield feeds
    feeds.clear_cache()


@pytest.fixture
def headlines(monkeypatch, store):
    rows = [_item("Gold hits a high", 1), _item("Silver follows", 2)]
    monkeypatch.setattr("backend.tools.news.items_for", lambda topic, limit=8: rows)
    return rows


# --- the tool ---------------------------------------------------------------

def test_get_news_returns_a_card_payload(headlines):
    result = registry.call("get_news", {"topic": "gold"})

    assert result["ok"] is True
    assert result["data"]["topic"] == "gold"
    assert len(result["data"]["items"]) == 2
    assert result["data"]["note"].startswith("as of ")
    assert "headlines" in result["message"]


def test_get_news_needs_a_topic():
    result = registry.call("get_news", {})

    assert result["ok"] is False and "topic" in result["message"].lower()


def test_an_unknown_topic_points_at_settings(store, monkeypatch):
    result = registry.call("get_news", {"topic": "blenders"})

    assert result["ok"] is False
    assert result["data"]["hint"] == "Add a feed in Settings \u2192 Feeds."


def test_a_network_failure_is_friendly_not_a_traceback(store, monkeypatch):
    def boom(topic, limit=8):  # noqa: ARG001
        raise feeds.FeedError("Couldn't reach example.com.", "unreachable")

    monkeypatch.setattr("backend.tools.news.items_for", boom)
    result = registry.call("get_news", {"topic": "gold"})

    assert result["ok"] is False
    assert result["data"]["hint"] == "Check your connection and try again."


def test_items_shape_matches_what_the_card_renders(store, monkeypatch):
    monkeypatch.setattr(
        store, "topic_items",
        lambda topic, limit=8: [
            {"title": "Gold up", "url": "https://k/1", "source": "Kitco",
             "ts": int(time.time()) - 7200, "snippet": "text"},
        ],
    )
    items = __import__("backend.tools.news", fromlist=["items_for"]).items_for("gold")

    assert set(items[0]) == {"title", "source", "when", "url", "snippet"}
    assert items[0]["when"] == "2h"


# --- the fast path ----------------------------------------------------------

def test_gold_news_is_a_fast_path_step_not_a_model_call():
    assert router.parse("gold news") == [{"action": "get_news", "topic": "gold"}]
    assert router.parse("gold news today") == [{"action": "get_news", "topic": "gold"}]
    assert router.parse("Crypto News") == [{"action": "get_news", "topic": "crypto"}]
    assert router.parse("latest silver news") == [{"action": "get_news",
                                                   "topic": "silver"}]
    assert router.parse("news about markets") == [{"action": "get_news",
                                                   "topic": "markets"}]


def test_aliases_reach_the_right_topic():
    assert router.parse("bitcoin news")[0]["topic"] == "bitcoin"
    assert router.parse("xau news")[0]["topic"] == "xau"
    # the tool resolves the alias, so the card still comes from the gold feeds
    assert feeds.topic_key("bitcoin") == "crypto"


def test_an_unknown_topic_falls_back_to_web_search():
    assert router.parse("ai news") == [{"action": "web_search", "query": "ai news"}]


def test_sentences_that_merely_end_in_news_go_to_the_model():
    assert router.parse("good news") is None
    assert router.parse("i have news for you") is None
    assert router.parse("breaking news about my package") is None
    assert router.parse("tell me the news") is None


def test_news_still_loses_to_an_explicit_site_search():
    assert router.parse("search gold news on bing")[0] == {
        "action": "search_in_browser", "site": "bing", "query": "gold news"}


def test_a_mixed_message_keeps_the_news_step():
    steps, rest = router.parse_parts("gold news and open youtube")

    assert steps[0] == {"action": "get_news", "topic": "gold"}
    assert rest == []
