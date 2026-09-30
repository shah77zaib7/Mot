"""Contacts + whatsapp_message: matching, the Confirm card, the link fallback.

No real chat is ever opened: launchers and the database are faked.
"""
from __future__ import annotations

import json

import pytest

from backend.core import contacts
from backend.tools import launch, registry, whatsapp

PEOPLE = [
    {"id": "mom", "name": "Mom", "phone": "+91 98765 43210", "aliases": ["mother"]},
    {"id": "om", "name": "Om", "phone": "+91 90000 00000", "aliases": []},
    {"id": "momita", "name": "Momita", "phone": "+91 91111 11111", "aliases": []},
]


@pytest.fixture(autouse=True)
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(contacts, "CONTACTS_PATH", tmp_path / "contacts.json")
    contacts.save({"contacts": json.loads(json.dumps(PEOPLE))})
    yield


@pytest.fixture
def launched(monkeypatch):
    """Record what would have been opened, and let a test fail the scheme."""
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


# --- matching (never guesses) -----------------------------------------------

def test_match_by_name_alias_and_case():
    assert contacts.match("mom")["id"] == "mom"
    assert contacts.match("MOM")["id"] == "mom"
    assert contacts.match("mother")["id"] == "mom"       # alias
    assert contacts.match("om")["id"] == "om"


def test_match_refuses_to_guess():
    assert contacts.match("m") is None        # three candidates
    assert contacts.match("stranger") is None  # nobody close
    assert contacts.match("") is None


def test_upsert_validates_and_normalises_aliases():
    saved = contacts.upsert({"name": "Ravi", "phone": "+91 91234 56789",
                             "aliases": "ravi bhai, ravi bhai,  bro"})

    assert saved["aliases"] == ["ravi bhai", "bro"]
    assert contacts.match("bro")["name"] == "Ravi"

    with pytest.raises(ValueError):
        contacts.upsert({"name": "", "phone": "12345"})
    with pytest.raises(ValueError):
        contacts.upsert({"name": "No phone", "phone": "12"})
    with pytest.raises(ValueError):
        contacts.upsert({"id": "someone-else", "name": "MOM",
                         "phone": "+91 90000 11111"})  # same person, other id


def test_delete_removes_one_contact():
    assert contacts.delete("om") is True
    assert contacts.match("om") is None
    assert contacts.delete("om") is False


# --- the tool ---------------------------------------------------------------

def test_whatsapp_stops_at_a_confirm_card(launched):
    result = registry.call("whatsapp_message", {"contact": "mom", "text": "hi mom"})

    assert result["ok"] is True
    assert result["data"]["needs_confirm"] is True
    assert result["data"]["contact"] == {"name": "Mom", "phone": "+91 98765 43210"}
    assert result["data"]["url"] == \
        "whatsapp://send?phone=919876543210&text=hi%20mom"
    assert result["data"]["fallback_url"] == \
        "https://wa.me/919876543210?text=hi%20mom"
    assert launched == []  # nothing opened before Confirm


def test_an_unknown_contact_is_reported_not_guessed():
    result = registry.call("whatsapp_message", {"contact": "Zara", "text": "hi"})

    assert result["ok"] is False
    assert "Zara" in result["message"]
    assert "Settings" in result["data"]["hint"]


def test_a_blank_message_is_refused():
    result = registry.call("whatsapp_message", {"contact": "mom", "text": "  "})

    assert result["ok"] is False and "no message" in result["message"]


def test_open_chat_prefers_the_desktop_link(launched):
    data = registry.call("whatsapp_message", {"contact": "mom", "text": "hi mom"})["data"]

    result = whatsapp.open_chat(data)

    assert result["ok"] is True
    assert launched[0] == ("scheme", "whatsapp://send?phone=919876543210&text=hi%20mom")
    assert len(launched) == 1


def test_open_chat_falls_back_to_wa_me_when_the_scheme_fails(monkeypatch, launched):
    data = registry.call("whatsapp_message", {"contact": "mom", "text": "hi mom"})["data"]
    monkeypatch.setattr(launch, "open_scheme",
                        lambda url: launched.append(("scheme", url)) or {"ok": False})

    result = whatsapp.open_chat(data)

    assert result["ok"] is True
    assert launched[0][0] == "scheme"
    assert launched[1] == ("url", "https://wa.me/919876543210?text=hi%20mom")
    assert "wa.me" in result["data"]["note"]


def test_open_chat_reports_failure_when_nothing_opens(monkeypatch, launched):
    data = registry.call("whatsapp_message", {"contact": "mom", "text": "hi"})["data"]
    monkeypatch.setattr(launch, "open_scheme", lambda url: {"ok": False})
    monkeypatch.setattr(launch, "open_url", lambda url, browser="default": {"ok": False})

    result = whatsapp.open_chat(data)

    assert result["ok"] is False and "Couldn" in result["message"]


# --- the card and the confirmation ------------------------------------------

def test_the_card_shows_the_contact_and_the_text():
    from backend.core import runner

    action = runner.run_steps(
        [{"action": "whatsapp_message", "contact": "mom", "text": "hi mom"}])[0]

    assert action["status"] == "needs_confirm"
    assert action["title"] == "Send \u201chi mom\u201d to Mom?"
    assert action["detail"] == "+91 98765 43210 \u00b7 WhatsApp"
    assert runner.summary([action]) == "Send \u201chi mom\u201d to Mom? Press Confirm to continue."


def test_an_unknown_contact_is_a_failed_card():
    from backend.core import runner

    action = runner.run_steps(
        [{"action": "whatsapp_message", "contact": "Zara", "text": "hi"}])[0]

    assert action["status"] == "failed"
    assert "Zara" in action["title"]
    assert "Contacts" in (action["detail"] or "")


def _stored_action(db, payload: dict) -> dict:
    chat = db.create_chat(title="t")
    db.add_message(chat["id"], "user", "whatsapp mom hi mom")
    message = db.add_message(chat["id"], "assistant", "Send?", actions=[payload])
    return message["actions"][0]


def test_confirming_opens_the_chat(fake_db, launched):
    from backend.api.actions import ConfirmIn, confirm_action

    stored = _stored_action(fake_db, {
        "id": "act-w1", "status": "needs_confirm", "title": "Send?",
        "data": registry.call("whatsapp_message",
                              {"contact": "mom", "text": "hi mom"})["data"],
    })

    result = confirm_action(stored["id"], ConfirmIn(confirm=True))

    assert result["action"]["status"] == "done"
    assert "Mom" in result["action"]["title"]
    assert launched[0][0] == "scheme"
    assert fake_db.find_action("act-w1")["status"] == "done"


def test_declining_sends_nothing(fake_db, launched):
    from backend.api.actions import ConfirmIn, confirm_action

    stored = _stored_action(fake_db, {
        "id": "act-w2", "status": "needs_confirm", "title": "Send?",
        "data": registry.call("whatsapp_message",
                              {"contact": "mom", "text": "hi mom"})["data"],
    })

    result = confirm_action(stored["id"], ConfirmIn(confirm=False))

    assert result["action"]["status"] == "cancelled"
    assert "nothing was sent" in result["action"]["message"]
    assert launched == []
    assert fake_db.find_action("act-w2")["status"] == "cancelled"
