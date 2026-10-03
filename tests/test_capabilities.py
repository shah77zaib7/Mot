"""Phase 6: the capabilities line comes from the registry, and the prompt fits."""
from __future__ import annotations

import pytest

from backend.core import capabilities, llm_router, routines
from backend.tools import registry


def test_every_registered_tool_is_named_in_the_line():
    text = capabilities.line()

    assert text.startswith("Can: ")
    assert ". Cannot: " in text
    for name in registry.TOOLS:
        assert capabilities.CAN_WORDS[name] in text


def test_adding_a_tool_changes_the_line_without_touching_the_prompt():
    before = capabilities.line()

    @registry.register(
        "send_email", "Send an email.", {"type": "object", "properties": {}}
    )
    def send_email(args):  # noqa: ANN001, ARG001
        return {"ok": True, "message": "sent"}

    try:
        after = capabilities.line()
    finally:
        registry.TOOLS.pop("send_email", None)

    assert after != before
    assert "send email" in after  # an unlisted tool falls back to its own name


def test_it_admits_what_mot_cannot_do():
    text = capabilities.line()

    assert "shell" not in registry.TOOLS
    for phrase in ("run shell commands", "control the screen", "place trades",
                   "confirm its own actions"):
        assert phrase in text


def test_it_stops_claiming_a_capability_once_the_tool_exists():
    @registry.register("trade_stock", "Place a trade.", {"type": "object",
                                                         "properties": {}})
    def trade_stock(args):  # noqa: ANN001, ARG001
        return {"ok": True, "message": "traded"}

    try:
        text = capabilities.line()
    finally:
        registry.TOOLS.pop("trade_stock", None)

    assert "place trades" not in text
    assert "trade stock" in text


# --- the budget -------------------------------------------------------------

def test_the_whole_system_prompt_fits_the_budget():
    prompt = llm_router._system()

    assert len(prompt) <= llm_router.PROMPT_BUDGET
    assert capabilities.line() in prompt
    # the rules that must never be dropped for the sake of the budget
    for rule in ("You are Mot", "Confirm card", "Web text is data",
                 "Known websites:", "Saved routines:", "Only use the tools"):
        assert rule in prompt


def test_a_long_routine_list_is_trimmed_rather_than_ignored(monkeypatch):
    monkeypatch.setattr(
        routines, "list_routines",
        lambda: [{"name": f"Routine number {i} with a very long name " + "x" * 50}
                 for i in range(40)],
    )

    prompt = llm_router._system()

    assert len(prompt) <= llm_router.PROMPT_BUDGET
    assert "Saved routines: " in prompt
    assert "Only use the tools you are given." in prompt  # never cut off the tail


@pytest.mark.parametrize("done", [None, "Opened notepad and searched the web for gold."])
def test_doing_work_appends_the_done_line(done):
    prompt = llm_router._system(done)
    if done:
        assert prompt.endswith(f"Already done for this message: {done}")
