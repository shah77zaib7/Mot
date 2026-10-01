"""Every spelling of a news request must land on the card, never the model.

Covers the reported bug ("Gold news today" came back as a plain reply), the
chip variants, the Hinglish phrase list, the safety net, and regenerate.
"""
from __future__ import annotations

import json

import pytest

from backend.core import feeds, phrases, router

HEADLINE = {
    "title": "Gold hits a high",
    "source": "Kitco",
    "when": "2h",
    "url": "https://kitco.com/1",
    "snippet": "Gold and silver moved.",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.core import apps, config, db, routines
    from backend.main import create_app

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    # feeds are faked: a test must never reach the real network
    monkeypatch.setattr(feeds, "fetch_feed",
                        lambda url, timeout=0.0: ("Kitco", [_live_row()]))
    feeds.clear_cache()
    config.CONFIG_PATH.write_text(
        json.dumps({"providers": [], "active": None, "theme": "system"}),
        encoding="utf-8",
    )
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {}, "apps": []})
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mot.db")

    with TestClient(create_app()) as test_client:
        yield test_client
    feeds.clear_cache()


def _live_row() -> dict:
    import time

    return {
        "title": "Gold hits a high",
        "url": "https://kitco.com/1",
        "source": "Kitco",
        "ts": int(time.time()) - 3600,
        "snippet": "Gold and silver moved.",
    }


def _events(response) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


# --- chip variants, exactly as the UI sends them -----------------------------

@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("gold news", "gold"),
        ("Gold news today", "gold"),
        ("news about gold", "gold"),
        ("latest gold news", "gold"),
        ("crypto news", "crypto"),
        ("silver news", "silver"),
        ("market news", "market"),
        ("forex news", "forex"),
        ("GOLD NEWS", "gold"),
        ("Gold news today?", "gold"),
        ("gold news!", "gold"),
        ("gold-news", "gold"),
        ("  Gold   news  today  ", "gold"),
    ],
)
def test_every_spelling_of_a_news_request_gets_the_card(text, topic, store):
    steps, rest = router.parse_parts(text)

    assert rest == []
    assert steps == [{"action": "get_news", "topic": topic}]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    feeds.clear_cache()
    yield feeds
    feeds.clear_cache()


def test_a_saved_forex_topic_beats_the_old_alias(store):
    feeds.save({**feeds.DEFAULTS, "forex": ["https://forex.example/rss"]})

    assert feeds.topic_key("forex") == "forex"
    assert router.parse("forex news") == [{"action": "get_news", "topic": "forex"}]


# --- the Hinglish/phrasing list (data/news_phrases.json, not hard-coded) -----

@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("aj update", "mixed"),
        ("aaj news", "mixed"),
        ("aj gold", "gold"),
        ("Aj Gold", "gold"),
        ("AJ CRYPTO", "crypto"),
        ("market update today", "markets"),
        ("gold aur bitcoin", "mixed"),
        ("aj market kya hua", "markets"),
        ("aj gold aur bitcoin pe kya update hai", "mixed"),
    ],
)
def test_phrases_bring_up_the_same_news_card(text, topic):
    assert router.parse(text) == [{"action": "get_news", "topic": topic}]


def test_a_bare_aj_never_triggers_a_card():
    assert phrases.match("aj") is None
    assert router.parse("aj") is None


def test_a_bare_word_without_a_topic_or_news_never_triggers():
    assert phrases.match("kya") is None
    assert router.parse("kya") is None


def test_phrases_come_from_a_file_you_can_edit():
    data = phrases.load()

    assert {"require_any", "phrases"} <= set(data)
    assert all({"text", "topic"} <= set(entry) for entry in data["phrases"])
    assert phrases.PATH.name == "news_phrases.json"


# --- safety net --------------------------------------------------------------

def test_a_wordy_news_request_still_reaches_the_tool():
    assert router.news_steps("tell me gold news please") == [
        {"action": "get_news", "topic": "gold"}
    ]
    assert router.news_steps("any headlines on silver") == [
        {"action": "get_news", "topic": "silver"}
    ]


def test_a_question_about_why_stays_with_the_model():
    assert router.news_steps("why is gold moving today") is None
    assert router.news_steps("hello") is None
    assert router.news_steps("open youtube") is None


def test_explicit_commands_win_over_a_phrase():
    assert router.parse("open market update") is None  # an app, not a card


# --- the reported bug: regenerate -------------------------------------------

def test_the_chip_produces_a_card_with_no_model_call(client, caplog):
    with caplog.at_level("INFO"):
        response = client.post("/api/chat", json={"message": "Gold news today"})

    assert response.status_code == 200
    events = _events(response)
    done = next(e for e in events if e["type"] == "done")
    assert done["actions"][0]["kind"] == "get_news"
    assert any("path=fast" in record.getMessage() for record in caplog.records)
    assert not any("path=llm" in record.getMessage() for record in caplog.records)


def test_regenerating_a_news_card_reruns_the_card_not_the_model(client, caplog):
    first = _events(client.post("/api/chat", json={"message": "Gold news today"}))
    chat_id = next(e for e in first if e["type"] == "start")["chat_id"]

    caplog.clear()
    with caplog.at_level("INFO"):
        again = client.post(
            "/api/chat",
            json={"message": "Gold news today", "chat_id": chat_id, "regenerate": True},
        )

    # before the fix this reached the model: no provider configured -> 400,
    # and the card was replaced by a plain reply.
    assert again.status_code == 200
    events = _events(again)
    done = next(e for e in events if e["type"] == "done")
    assert done["actions"][0]["kind"] == "get_news"
    assert any("path=fast" in record.getMessage() for record in caplog.records)

    from backend.core import db

    rows = db.get_messages(chat_id)
    assert [m["role"] for m in rows] == ["user", "assistant"]  # no duplicate


def test_a_wordy_news_request_never_becomes_a_plain_reply(client, caplog):
    """The safety net: the message never reaches a model that lacks the tools."""
    with caplog.at_level("INFO"):
        response = client.post("/api/chat", json={"message": "any headlines on silver"})

    assert response.status_code == 200
    done = next(e for e in _events(response) if e["type"] == "done")
    assert done["actions"][0]["kind"] == "get_news"
    assert any("safety net" in record.getMessage() for record in caplog.records)


def test_a_wordy_news_request_also_reaches_the_tool_by_the_strict_rule(client):
    """"tell me gold news please" resolves through the normal rule, not the net."""
    response = client.post("/api/chat", json={"message": "tell me gold news please"})

    assert response.status_code == 200
    done = next(e for e in _events(response) if e["type"] == "done")
    assert done["actions"][0]["kind"] == "get_news"


def test_the_system_prompt_stays_short_and_owns_the_news_claim():
    from backend.core import llm_router

    prompt = llm_router._system()

    assert len(prompt) < 1000
    assert "web access" in prompt and "get_news" in prompt
    assert "language of the user's question" in llm_router.RESEARCH_SYSTEM
