"""Settings > Feeds API + the fast-path news card end to end (no model)."""
from __future__ import annotations

import json

import pytest

from backend.core import apps, config, feeds, router, routines

FAKE_APPS = [
    {"name": "WhatsApp", "kind": "uwp", "target": "id!App", "args": ""},
    {"name": "Google Chrome", "kind": "app", "target": r"C:\x.exe", "args": ""},
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    feeds.clear_cache()
    config.CONFIG_PATH.write_text(json.dumps(
        {"providers": [], "active": None, "theme": "system"}), encoding="utf-8")
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {}, "apps": FAKE_APPS})

    from backend.core import db
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mot.db")

    with TestClient(create_app()) as test_client:
        yield test_client
    feeds.clear_cache()
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None


# --- the endpoints ----------------------------------------------------------

def test_get_feeds_ships_the_four_defaults(client):
    body = client.get("/api/feeds").json()

    assert set(body["topics"]) == {"gold", "silver", "crypto", "markets"}
    assert body["defaults"]["gold"][0].startswith("https://")
    assert body["aliases"]["bitcoin"] == "crypto"


def test_put_feeds_saves_and_drops_the_cache(client):
    body = client.put("/api/feeds", json={"topics": {
        "gold": ["https://a.example/rss", " https://b.example/rss "],
        "oil": [],
    }}).json()

    assert body["ok"] is True
    assert body["topics"]["gold"] == ["https://a.example/rss", "https://b.example/rss"]
    assert "oil" not in body["topics"]  # empty topics are dropped, not saved
    assert json.loads(feeds.FEEDS_PATH.read_text(encoding="utf-8"))["gold"][0] == \
        "https://a.example/rss"


def test_put_feeds_rejects_junk_urls_and_empty_lists(client):
    bad = client.put("/api/feeds", json={"topics": {"gold": ["ftp://x/feed"]}}).json()
    empty = client.put("/api/feeds", json={"topics": {}}).json()

    assert bad["ok"] is False and "http" in bad["message"]
    assert empty["ok"] is False and "at least one" in empty["message"]


def test_test_feed_endpoint_reports_counts(client, serve):
    rss = ('<?xml version="1.0"?><rss version="2.0"><channel><title>Kitco</title>'
           "<item><title>Gold up</title><link>https://k/1</link></item>"
           "</channel></rss>")
    base = serve({"/feed.xml": (200, rss), "/broken.xml": (500, "nope")})

    ok = client.post("/api/feeds/test", json={"url": f"{base}/feed.xml"}).json()
    fail = client.post("/api/feeds/test", json={"url": f"{base}/broken.xml"}).json()
    junk = client.post("/api/feeds/test", json={"url": "not a url"}).json()

    assert ok["ok"] and ok["count"] == 1 and "Kitco" in ok["message"]
    assert not fail["ok"] and "HTTP 500" in fail["message"]
    assert not junk["ok"]


# --- the fast path end to end ------------------------------------------------

def test_gold_news_streams_a_card_with_no_model_at_all(client, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a news card must never call the model")

    monkeypatch.setattr("backend.core.llm_router.route", explode)
    monkeypatch.setattr("backend.core.llm.stream_chat", explode)
    monkeypatch.setattr(
        "backend.tools.news.items_for",
        lambda topic, limit=8: [{"title": "Gold hits a high", "source": "Kitco",
                                 "when": "2h", "url": "https://kitco.com/1",
                                 "snippet": "Gold rose."}],
    )

    events = _sse(client.post("/api/chat", json={"message": "gold news today"}).text)
    done = events[-1]

    assert done["type"] == "done"
    action = done["actions"][0]
    assert action["kind"] == "get_news"
    assert action["status"] == "done"
    assert action["data"]["items"][0]["title"] == "Gold hits a high"
    assert action["data"]["items"][0]["url"] == "https://kitco.com/1"
    assert "gold headlines" in done["text"].lower()


def test_the_model_is_not_consulted_for_any_known_topic(client, monkeypatch):
    monkeypatch.setattr("backend.core.llm_router.route",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(
        "backend.tools.news.items_for",
        lambda topic, limit=8: [{"title": "x", "source": "s", "when": "1h",
                                 "url": "https://x/1", "snippet": ""}],
    )

    for message in ("silver news", "crypto news", "markets news", "bitcoin news"):
        done = _sse(client.post("/api/chat", json={"message": message}).text)[-1]
        assert done["type"] == "done", message


def _sse(body: str) -> list[dict]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


# --- the background refresh ---------------------------------------------------

def test_the_feeds_endpoint_reports_the_refresh_state(client):
    body = client.get("/api/feeds").json()

    assert body["ingest"]["enabled"] is True
    assert body["ingest"]["interval_hours"] == 2.0
    assert body["ingest"]["last_ingest_at"] is None
    assert isinstance(body["sources"], list)


def test_the_refresh_controls_round_trip(client):
    saved = client.put("/api/feeds/ingest",
                       json={"enabled": False, "interval_hours": 4}).json()

    assert saved["ok"] is True
    assert saved["ingest"]["enabled"] is False
    assert saved["ingest"]["interval_hours"] == 4.0
    assert client.get("/api/feeds").json()["ingest"]["interval_hours"] == 4.0


def test_refresh_now_runs_the_job_without_the_network(client, monkeypatch, tmp_path):
    from backend.core import feeds, snapshot

    monkeypatch.setattr(
        feeds, "refresh_all",
        lambda: snapshot.write({"gold": []}, {"https://a/rss": ""}),
    )
    body = client.post("/api/feeds/refresh").json()

    assert body["ok"] is True
    assert body["ingest"]["last_ingest_at"] is not None
    assert body["ingest"]["sources"] == 1
