"""Runner + action cards + the fast path end to end (model turned off).

No test here opens a real app, browser or installer.
"""
from __future__ import annotations

import json
import sys
import time

import pytest

from backend.core import actions, apps, config, routines
from backend.tools import install, launch

FAKE_APPS = [
    {"name": "WhatsApp", "kind": "uwp", "target": "5319275A.WhatsAppDesktop!App", "args": ""},
    {"name": "Google Chrome", "kind": "app",
     "target": r"C:\Program Files\Google\Chrome\Application\chrome.exe", "args": ""},
]


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    config.CONFIG_PATH.write_text(
        json.dumps({"providers": [], "active": None, "theme": "system"}),  # no model at all
        encoding="utf-8",
    )
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {}, "apps": FAKE_APPS})
    yield


@pytest.fixture
def fake_db(tmp_path, monkeypatch):
    from backend.core import db

    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mot.db")
    yield db
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None


@pytest.fixture
def opened(monkeypatch):
    """Record everything that would have been launched."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        launch, "open_url",
        lambda url, browser="default": calls.append(("url", url)) or {"ok": True},
    )
    monkeypatch.setattr(launch, "_spawn", lambda args: calls.append(("spawn", tuple(args))))
    return calls


@pytest.fixture
def client(files, fake_db, opened):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def sse_events(body: str) -> list[dict]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


# --- fast path through the API -------------------------------------------

def test_fast_path_runs_with_no_model_at_all(client):
    response = client.post(
        "/api/chat", json={"message": "open YouTube and search lo-fi"}
    )

    assert response.status_code == 200
    events = sse_events(response.text)
    kinds = [event["type"] for event in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert kinds.count("action") >= 2  # running + done for the one step

    done = events[-1]
    assert [a["kind"] for a in done["actions"]] == ["search_in_browser"]
    assert [a["status"] for a in done["actions"]] == ["done"]
    assert "YouTube" in done["actions"][0]["message"]
    assert "litellm" not in sys.modules  # the model was never touched

    chat_id = done["chat_id"]
    stored = client.get(f"/api/chats/{chat_id}").json()["messages"]
    assistant = [m for m in stored if m["role"] == "assistant"][0]
    assert assistant["content"] == "Searched YouTube for \u201clo-fi\u201d."
    assert [a["status"] for a in assistant["actions"]] == ["done"]


def test_plain_chat_without_a_model_stays_friendly(client):
    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 400
    assert "No model chosen" in response.json()["detail"]


def test_routine_command_runs_every_step(client):
    response = client.post("/api/chat", json={"message": "morning setup"})

    assert response.status_code == 200
    events = sse_events(response.text)
    final = events[-1]["actions"][0]
    assert final["kind"] == "run_routine"
    assert final["status"] == "done"
    assert len(final["steps"]) == 3  # TradingView chart, Chrome, WhatsApp
    assert all(step["status"] == "done" for step in final["steps"])


# --- runner ----------------------------------------------------------------

def test_runner_reports_running_then_done():
    from backend.core import router, runner

    seen: list[dict] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(launch, "open_url", lambda url, browser="default": {"ok": True})
        plan = router.parse("open youtube")
        actions_out = runner.run_steps(plan, emit=seen.append, chat_id="c1")

    assert [event["status"] for event in seen] == ["running", "done"]
    assert actions_out[0]["title"] == "Opened youtube.com"
    assert actions_out[0]["phrase"] == "opened youtube.com"


def test_app_not_found_is_a_failed_card():
    from backend.core import runner

    action = runner.run_steps([{"action": "open_app", "name": "zzz not real"}])[0]

    assert action["status"] == "failed"
    assert "install zzz not real" in (action["detail"] or "")


def test_summary_joins_phrases():
    from backend.core import runner

    done = {"status": "done", "phrase": "opened youtube.com"}
    also = {"status": "done", "phrase": "searched YouTube for \u201clo-fi\u201d"}
    failed = {"status": "failed", "message": "Couldn\u2019t open x."}
    pending = {"status": "needs_confirm", "title": "Install VLC?"}

    assert runner.summary([done]) == "Opened youtube.com."
    assert runner.summary([done, also]) == \
        "Opened youtube.com and searched YouTube for \u201clo-fi\u201d."
    assert runner.summary([failed]) == "Couldn\u2019t open x."
    assert runner.summary([pending]) == "Install VLC? Press Confirm to continue."


# --- install confirmation --------------------------------------------------

def _stored_action(db, body: dict) -> dict:
    chat = db.create_chat(title="t")
    db.add_message(chat["id"], "user", "install vlc")
    message = db.add_message(chat["id"], "assistant", "Install VLC?", actions=[body])
    return message["actions"][0]


def test_install_stops_at_confirmation(fake_db, monkeypatch):
    from backend.core import runner

    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(
        install, "run_winget",
        lambda args, timeout=0, on_line=None: (0, "Name Id Version\nx"),
    )
    monkeypatch.setattr(
        install, "parse_search",
        lambda out: [{"name": "VideoLAN VLC", "id": "VideoLAN.VLC", "version": "3.0.20"}],
    )

    action = runner.run_steps([{"action": "install_app", "name": "vlc"}])[0]

    assert action["status"] == "needs_confirm"
    assert action["title"] == "Install VideoLAN VLC?"
    assert action["data"]["package"]["id"] == "VideoLAN.VLC"


def test_declining_does_not_install(fake_db, monkeypatch):
    from backend.api.actions import ConfirmIn, confirm_action

    installed: list = []
    monkeypatch.setattr(install, "install", lambda pkg, on_line=None: installed.append(pkg))
    stored = _stored_action(fake_db, {
        "id": "act-1", "status": "needs_confirm", "title": "Install VLC?",
        "data": {"package": {"id": "VideoLAN.VLC", "name": "VLC"}},
    })

    result = confirm_action(stored["id"], ConfirmIn(confirm=False))

    assert result["action"]["status"] == "cancelled"
    assert installed == []
    assert fake_db.find_action("act-1")["status"] == "cancelled"


def test_confirming_runs_winget_and_publishes_progress(fake_db, monkeypatch):
    from backend.api.actions import ConfirmIn, confirm_action

    monkeypatch.setattr(install, "winget_available", lambda: True)
    monkeypatch.setattr(
        install, "install",
        lambda pkg, on_line=None: {"ok": True, "message": f"Installed {pkg['name']}."},
    )
    stored = _stored_action(fake_db, {
        "id": "act-2", "status": "needs_confirm", "title": "Install VLC?",
        "data": {"package": {"id": "VideoLAN.VLC", "name": "VLC"}},
    })
    queue = actions.subscribe()
    try:
        confirm_action(stored["id"], ConfirmIn(confirm=True))

        deadline = time.time() + 5
        while time.time() < deadline:
            saved = fake_db.find_action("act-2")
            if saved["status"] == "done":
                break
            time.sleep(0.05)
    finally:
        actions.unsubscribe(queue)

    saved = fake_db.find_action("act-2")
    assert saved["status"] == "done"
    assert saved["title"] == "Installed VLC"
    assert not queue.empty()  # the UI was told about it


# --- default routine -------------------------------------------------------

def test_the_default_morning_setup_ships(files):
    routine = routines.get("morning setup")

    assert routine is not None
    assert routine["steps"][0]["url"].startswith("https://www.tradingview.com/chart/")
    assert routine["steps"][1] == {"action": "open_app", "name": "chrome"}
    assert routine["steps"][2] == {"action": "open_app", "name": "whatsapp"}


def test_routines_crud(files):
    saved = routines.upsert({"name": "Deep work", "steps": [
        {"action": "open_url", "url": "https://focus@example"}]})
    assert routines.get(saved["id"])["name"] == "Deep work"

    with pytest.raises(ValueError):
        routines.upsert({"name": "", "steps": []})
    with pytest.raises(ValueError):
        routines.upsert({"name": "x", "steps": []})

    assert routines.delete(saved["id"]) is True
    assert routines.get(saved["id"]) is None


# --- Phase 4: news cards ----------------------------------------------------

def test_news_card_carries_headlines_for_the_frontend(files, monkeypatch):
    from pathlib import Path

    from backend.core import feeds, router, runner
    from backend.tools import news as news_tool

    monkeypatch.setattr(feeds, "FEEDS_PATH", Path("Z:/definitely/missing/feeds.json"))
    monkeypatch.setattr(
        news_tool, "items_for",
        lambda topic, limit=8: [{"title": "Gold hits a high", "source": "Kitco",
                                 "when": "2h", "url": "https://k/1", "snippet": ""}],
    )
    action = runner.run_steps(router.parse("gold news"))[0]

    assert action["kind"] == "get_news"
    assert action["status"] == "done"
    assert action["detail"].startswith("as of ")
    assert action["title"].endswith("headlines, newest first")
    assert action["data"]["items"][0]["title"] == "Gold hits a high"
    assert "gold headlines" in action["phrase"]


def test_web_search_card_title_and_phrase(files, monkeypatch):
    from backend.core import router, runner
    from backend.tools import websearch

    monkeypatch.setattr(websearch, "_search", lambda q, n: [  # noqa: ARG005
        {"title": "Something", "source": "kitco.com", "when": "14:32",
         "url": "https://k/1", "snippet": "x"}])
    websearch._CACHE.clear()
    action = runner.run_steps(router.parse("ai news"))[0]

    assert action["kind"] == "web_search"
    assert action["status"] == "done"
    assert action["data"]["items"]
    assert "searched the web" in action["phrase"]


def test_a_failed_news_fetch_shows_a_hint_not_a_traceback(files, monkeypatch):
    from backend.core import feeds, router, runner

    def boom(url, timeout=0.0):  # noqa: ARG001
        raise feeds.FeedError("Couldn't reach example.com.", "unreachable")

    monkeypatch.setattr(feeds, "fetch_feed", boom)
    monkeypatch.setattr(feeds, "load", lambda: {"gold": ["https://example.com/rss"]})
    action = runner.run_steps(router.parse("gold news"))[0]

    assert action["status"] == "failed"
    assert action["detail"] == "Check your connection and try again."
    assert "Traceback" not in action["message"]
