"""The background refresh, the saved snapshot it writes, and the offline path.

Everything here is offline: feeds are faked and the clock is the test's clock.
"""
from __future__ import annotations

import json
import logging
import time

import pytest

from backend.core import feeds, ingest, snapshot
from backend.tools import news


def _row(title: str, hours_old: float = 1.0, url: str = "https://kitco.com/1") -> dict:
    return {
        "title": title,
        "url": url,
        "source": "Kitco",
        "ts": int(time.time() - hours_old * 3600),
        "snippet": "Gold and silver moved.",
    }


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    feeds.clear_cache()
    yield feeds
    feeds.clear_cache()


def _save_snapshot(topics: dict, sources: dict, age_hours: float = 0.0) -> None:
    """Write the file as refresh_all() would, then backdate it."""
    now = int(time.time())
    payload = {
        "fetched_at": time.time() - age_hours * 3600,
        "topics": {
            topic: [
                {
                    "title": item["title"],
                    "url": item["url"],
                    "source": item["source"],
                    "published_at": item["ts"],
                    "fetched_at": now,
                    "topic": topic,
                }
                for item in items
            ]
            for topic, items in topics.items()
        },
        "sources": sources,
    }
    snapshot.PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot.PATH.write_text(json.dumps(payload), encoding="utf-8")


# --- the job -----------------------------------------------------------------

def test_the_job_writes_headlines_and_links_only(store, monkeypatch, caplog):
    feeds.save({"gold": ["https://ok/rss"], "crypto": ["https://dead/rss"]})

    def fake(url, timeout=0.0):  # noqa: ARG001
        if "dead" in url:
            raise feeds.FeedError("gone", "unreachable")
        return "Kitco", [_row("Gold hits a high")]

    monkeypatch.setattr(feeds, "fetch_feed", fake)

    with caplog.at_level(logging.INFO):
        summary = feeds.refresh_all()

    saved = json.loads(snapshot.PATH.read_text(encoding="utf-8"))
    item = saved["topics"]["gold"][0]
    assert set(item) == {"title", "url", "source", "published_at", "fetched_at", "topic"}
    assert "snippet" not in item  # headlines and links only, never article text
    assert saved["topics"]["crypto"] == []
    assert saved["sources"]["https://dead/rss"] == "gone"

    # one dead feed never fails the run, and every source is logged
    assert summary["topics"] == {"gold": 1, "crypto": 0}
    assert summary["sources"] == 2 and summary["failed"] == 1
    assert "ingest ok:" in caplog.text and "ingest dead: gone" in caplog.text


def test_a_fresh_snapshot_answers_without_touching_the_network(store, monkeypatch):
    feeds.save({"gold": ["https://a/rss"]})
    _save_snapshot({"gold": [_row("Saved gold story")]}, {"https://a/rss": ""})

    def no_network(url, timeout=0.0):  # noqa: ARG001
        raise AssertionError("the network was used for a fresh snapshot")

    monkeypatch.setattr(feeds, "fetch_feed", no_network)
    result = news.get_news({"topic": "gold"})

    assert result["ok"] is True
    assert result["data"]["items"][0]["title"] == "Saved gold story"
    assert result["data"]["offline"] is False
    assert result["data"]["failed"] == 0


def test_an_old_snapshot_costs_exactly_one_live_read(store, monkeypatch):
    feeds.save({"gold": ["https://a/rss"]})
    _save_snapshot({"gold": [_row("Saved story", hours_old=9)]},
                   {"https://a/rss": ""}, age_hours=4)
    calls: list[str] = []

    def fake(url, timeout=0.0):  # noqa: ARG001
        calls.append(url)
        return "Kitco", [_row("Live story")]

    monkeypatch.setattr(feeds, "fetch_feed", fake)
    result = news.get_news({"topic": "gold"})

    assert result["ok"] is True and calls == ["https://a/rss"]
    assert result["data"]["items"][0]["title"] == "Live story"
    assert result["data"]["offline"] is False


def test_offline_serves_the_saved_snapshot_labelled_offline(store, monkeypatch):
    feeds.save({"gold": ["https://a/rss"]})
    _save_snapshot({"gold": [_row("Saved story")]}, {"https://a/rss": "no route"},
                   age_hours=5)

    def dead(url, timeout=0.0):  # noqa: ARG001
        raise feeds.FeedError("Couldn't reach a/rss.", "unreachable")

    monkeypatch.setattr(feeds, "fetch_feed", dead)
    result = news.get_news({"topic": "gold"})

    assert result["ok"] is True
    assert result["data"]["offline"] is True
    assert result["data"]["note"].endswith("(offline)")
    assert result["data"]["items"][0]["title"] == "Saved story"


def test_nothing_at_all_is_a_retry_card_not_a_model_reply(store, monkeypatch):
    feeds.save({"gold": ["https://a/rss"]})

    def dead(url, timeout=0.0):  # noqa: ARG001
        raise feeds.FeedError("nope", "unreachable")

    monkeypatch.setattr(feeds, "fetch_feed", dead)
    result = news.get_news({"topic": "gold"})

    assert result["ok"] is False
    assert result["message"] == "Couldn't reach the news sources."
    assert result["data"]["retry"] is True


# --- settings and the loop ---------------------------------------------------

def test_refresh_settings_round_trip_and_stay_in_range():
    saved = ingest.save({"enabled": False, "interval_hours": 6})
    assert saved["enabled"] is False and saved["interval_hours"] == 6
    assert ingest.settings()["enabled"] is False
    assert ingest.settings()["last_ingest_at"] is None  # nothing has run yet

    assert ingest.save({"interval_hours": 1000})["interval_hours"] == 24.0
    assert ingest.save({"interval_hours": 0})["interval_hours"] == 0.25
    assert ingest.save({"interval_hours": "soon"})["interval_hours"] == 2.0
    assert ingest.save({"enabled": True})["enabled"] is True


def test_the_loop_refreshes_once_at_startup_then_waits(monkeypatch):
    runs: list[float] = []
    monkeypatch.setattr(ingest, "refresh_now",
                        lambda: runs.append(time.time()) or {"ok": True})
    monkeypatch.setattr(ingest, "settings",
                        lambda: {"enabled": True, "interval_hours": 2.0,
                                 "last_ingest_at": None})

    ingest.start()
    deadline = time.time() + 5
    while not runs and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.2)
    ingest.stop()

    assert len(runs) == 1  # one pass now; the next is two hours away


def test_start_is_idempotent(monkeypatch):
    monkeypatch.setattr(ingest, "refresh_now", lambda: {"ok": True})
    ingest.start()
    first = ingest._thread
    ingest.start()
    assert ingest._thread is first
    ingest.stop()
