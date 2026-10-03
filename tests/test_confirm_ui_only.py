"""Phase 6: a model can never confirm its own install or WhatsApp card.

Confirmation is a UI route — `POST /api/actions/{id}` — and nothing the model
writes can reach it: unknown arguments are stripped, there is no confirm tool,
and the runner always stops at `needs_confirm`.
"""
from __future__ import annotations

import json

import pytest

from backend.core import llm_router, runner
from backend.tools import launch, registry

PEOPLE = [{"id": "mom", "name": "Mom", "phone": "+91 98765 43210", "aliases": ["mother"]}]


@pytest.fixture(autouse=True)
def files(tmp_path, monkeypatch):
    from backend.core import contacts

    monkeypatch.setattr(contacts, "CONTACTS_PATH", tmp_path / "contacts.json")
    contacts.save({"contacts": json.loads(json.dumps(PEOPLE))})
    yield


@pytest.fixture
def launched(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        launch, "open_scheme",
        lambda url: calls.append(("scheme", url)) or {"ok": True},
    )
    monkeypatch.setattr(
        launch, "open_url",
        lambda url, browser="default": calls.append(("url", url)) or {"ok": True},
    )
    return calls


@pytest.fixture
def winget(monkeypatch):
    from backend.tools import install

    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(
        install, "run_winget",
        lambda args, timeout=0, on_line=None: (0, "Name Id Version\nx"),
    )
    monkeypatch.setattr(
        install, "parse_search",
        lambda out: [{"name": "VideoLAN VLC", "id": "VideoLAN.VLC", "version": "3.0.20"}],
    )
    return install


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


# --- the model has no way in ------------------------------------------------

def test_the_registry_offers_nothing_that_can_confirm():
    names = list(registry.TOOLS)
    banned = ("confirm", "approve", "accept", "authorise", "authorize")
    assert [n for n in names if any(word in n for word in banned)] == []


def test_a_confirm_action_the_model_makes_up_is_not_a_tool():
    assert llm_router.validate([{"tool": "confirm", "args": {}}]) == \
        "unknown tool 'confirm'"
    assert llm_router.validate([{"tool": "confirm_action", "args": {"id": "x"}}]) == \
        "unknown tool 'confirm_action'"


def test_a_confirmation_flag_in_the_arguments_is_stripped():
    steps = [{"tool": "install_app",
              "args": {"name": "vlc", "confirm": "true", "approved": "yes",
                       "status": "done"}}]

    assert llm_router.validate(steps) is None  # unknown keys are dropped, not fatal
    assert set(steps[0]["args"]) == {"name"}
    assert llm_router.to_plan(steps) == [{"action": "install_app", "name": "vlc"}]


def test_the_install_card_is_never_pre_confirmed(winget):
    steps = [{"tool": "install_app", "args": {"name": "vlc", "confirm": "true"}}]
    llm_router.validate(steps)

    action = runner.run_steps(llm_router.to_plan(steps))[0]

    assert action["status"] == "needs_confirm"
    assert "confirm" not in (action.get("data") or {})
    assert action["data"]["package"]["id"] == "VideoLAN.VLC"


def test_the_whatsapp_card_is_never_pre_confirmed(launched):
    steps = [{"tool": "whatsapp_message",
              "args": {"contact": "mom", "text": "hi mom", "confirm": "yes"}}]
    llm_router.validate(steps)

    action = runner.run_steps(llm_router.to_plan(steps))[0]

    assert action["status"] == "needs_confirm"
    assert launched == []  # nothing opened before the user pressed Confirm


# --- the only way through is the UI route ----------------------------------

def test_confirmation_only_flows_through_the_ui_route(fake_db, winget):
    from fastapi import HTTPException

    from backend.api.actions import ConfirmIn, confirm_action

    chat = fake_db.create_chat(title="t")
    stored = fake_db.add_message(chat["id"], "assistant", "Install?", actions=[{
        "id": "act-model-cannot-make-this-up",
        "kind": "install_app", "title": "Install VideoLAN VLC?",
        "detail": "VideoLAN.VLC · winget", "status": "needs_confirm",
        "data": {"package": {"name": "VideoLAN VLC", "id": "VideoLAN.VLC"}},
        "message": "", "phrase": "", "steps": None, "chat_id": chat["id"],
    }])["actions"][0]

    assert stored["status"] == "needs_confirm"

    # Declining ends the card: it can never be confirmed afterwards.
    confirm_action(stored["id"], ConfirmIn(confirm=False))
    with pytest.raises(HTTPException) as declined:
        confirm_action(stored["id"], ConfirmIn(confirm=True))
    assert declined.value.status_code == 400

    # An action the model invented simply does not exist.
    with pytest.raises(HTTPException) as invented:
        confirm_action("deadbeefdeadbeef", ConfirmIn(confirm=True))
    assert invented.value.status_code == 404
