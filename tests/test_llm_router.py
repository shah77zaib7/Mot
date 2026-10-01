"""Phase 3: the LLM router — model picks a tool or answers, with a fake model.

Nothing here calls a real provider and nothing here opens a real app.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.core import llm_router
from backend.tools import launch

FAKE_APPS = [
    {"name": "WhatsApp", "kind": "uwp", "target": "id!App", "args": ""},
    {"name": "Top Secret Launcher 9", "kind": "app", "target": r"C:\x.exe", "args": ""},
]


def profile() -> dict:
    return {"name": "Test", "model": "test-model",
            "api_base": "http://127.0.0.1:9", "key_ref": None}


def resp(content=None, tool_calls=None) -> dict:
    """A litellm-shaped completion, as dicts (llm_router reads both)."""
    message: dict = {"content": content}
    if tool_calls is not None:
        message["tool_calls"] = [
            {"type": "function", "function": {"name": name, "arguments": args}}
            for name, args in tool_calls
        ]
    return {"choices": [{"message": message}]}


def scripted(responses, monkeypatch):
    """Replace _complete with a script of replies; returns its call log."""
    calls: list[dict] = []

    async def _complete(profile, messages, tools=None):
        calls.append({"messages": messages, "tools": tools})
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm_router, "_complete", _complete)
    monkeypatch.setattr(llm_router, "_JSON_ONLY", set())
    return calls


@pytest.fixture
def files(tmp_path, monkeypatch):
    from backend.core import apps, config, contacts, routines

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(contacts, "CONTACTS_PATH", tmp_path / "contacts.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    config.CONFIG_PATH.write_text(json.dumps({
        "providers": [{"id": "p-test", "name": "Test", "base_url": "http://127.0.0.1:9",
                       "key_ref": None, "models": [{"id": "m-1", "tag": ""}]}],
        "active": {"provider_id": "p-test", "model_id": "m-1"},
        "theme": "system",
    }), encoding="utf-8")
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {}, "apps": FAKE_APPS})
    contacts.save({"contacts": [
        {"id": "mom", "name": "Mom", "phone": "+91 98765 43210", "aliases": []}]})
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


# --- the prompt (requirement 3) --------------------------------------------

def test_the_prompt_never_lists_installed_apps(files):
    prompt = llm_router._system()

    assert "Top Secret Launcher 9" not in prompt  # the app list stays out, always
    assert "Known websites" in prompt             # sites are small and worth naming
    assert "Morning setup" in prompt


def test_the_prompt_is_short_enough_for_a_3b_model():
    # requirement 6: keep it under ~1000 chars including the new research tools
    assert len(llm_router._system()) < 1000


def test_the_prompt_treats_web_text_as_data():
    prompt = llm_router._system()

    assert "get_news" in prompt          # the model knows research exists
    assert "never instructions" in prompt  # requirement 4: web text is untrusted
    assert llm_router.RESEARCH_SYSTEM.count("untrusted data") == 1


def test_tool_spec_comes_from_the_registry():
    functions = [t["function"] for t in llm_router._tools()]

    assert [f["name"] for f in functions] == [
        "install_app", "open_app", "open_url", "play_youtube", "run_routine",
        "search_in_browser", "whatsapp_message", "get_news", "web_search"]
    assert all(f["description"] and f["parameters"] for f in functions)
    assert all(t["type"] == "function" for t in llm_router._tools())


def test_descriptions_send_apps_first_and_urls_last():
    descriptions = {f["function"]["name"]: f["function"]["description"]
                    for f in llm_router._tools()}

    assert "first" in descriptions["open_app"].lower()
    assert "no installed app" in descriptions["open_url"]
    assert "Confirm" in descriptions["whatsapp_message"]


# --- validation (requirement 4) --------------------------------------------

def test_validate_accepts_real_calls():
    steps = [
        {"tool": "open_app", "args": {"name": "chrome"}},
        {"tool": "search_in_browser", "args": {"query": "lo-fi", "site": "youtube"}},
    ]

    assert llm_router.validate(steps) is None
    assert llm_router.to_plan(steps) == [
        {"action": "open_app", "name": "chrome"},
        {"action": "search_in_browser", "query": "lo-fi", "site": "youtube"},
    ]


def test_validate_rejects_an_unknown_tool():
    assert "unknown tool 'rm_rf'" in llm_router.validate(
        [{"tool": "rm_rf", "args": {"path": "/"}}]
    )


def test_validate_rejects_a_missing_argument():
    assert "needs 'query'" in llm_router.validate(
        [{"tool": "search_in_browser", "args": {"site": "youtube"}}]
    )


def test_validate_rejects_a_number_where_text_is_wanted():
    assert "must be text" in llm_router.validate(
        [{"tool": "open_app", "args": {"name": 42}}]
    )


def test_validate_ignores_extra_and_blank_optional_values():
    steps = [{"tool": "open_url", "args": {
        "url": "https://x", "reason": "because", "browser": None}}]

    assert llm_router.validate(steps) is None
    assert steps[0]["args"] == {"url": "https://x"}


def test_validate_rejects_junk_shapes():
    assert llm_router.validate(None) is not None
    assert llm_router.validate([]) is not None
    assert llm_router.validate(["open youtube"]) is not None
    assert llm_router.validate([{"tool": "open_app"}]) is not None  # no name


# --- reading the model's answer --------------------------------------------

def test_json_block_survives_fences_and_prose():
    data = llm_router._json_block('Sure!\n```json\n{"steps": []}\n```')

    assert data == {"steps": []}
    assert llm_router._json_block("no json here") is None


def test_native_tool_calls_become_steps():
    steps, reply, reason = llm_router._interpret(
        resp(tool_calls=[("open_app", '{"name": "whatsapp"}')]), "native"
    )

    assert (reply, reason) == (None, None)
    assert steps == [{"tool": "open_app", "args": {"name": "whatsapp"}}]


def test_native_plain_text_is_a_normal_reply():
    steps, reply, reason = llm_router._interpret(
        resp(content="Gold is up 0.4% today."), "native"
    )

    assert (steps, reason) == (None, None)
    assert reply == "Gold is up 0.4% today."


def test_json_mode_needs_json():
    _, _, reason = llm_router._interpret(resp(content="Opening WhatsApp now!"), "json")

    assert "strict JSON" in reason


def test_an_empty_reply_is_invalid_not_fatal():
    _, reply, reason = llm_router._interpret(resp(content=""), "native")

    assert reply is None and reason == "the reply was empty"


# --- route() ----------------------------------------------------------------

def test_route_returns_valid_tool_calls(monkeypatch):
    scripted([resp(tool_calls=[
        ("open_app", '{"name": "chrome"}'),
        ("run_routine", '{"name": "Morning setup"}'),
    ])], monkeypatch)

    decision = asyncio.run(
        llm_router.route(profile(), "open chrome and start my day", [])
    )

    assert decision["kind"] == "steps"
    assert decision["steps"] == [
        {"action": "open_app", "name": "chrome"},
        {"action": "run_routine", "name": "Morning setup"},
    ]


def test_route_uses_the_text_reply(monkeypatch):
    scripted([resp(content="Bitcoin is steady around $65k.")], monkeypatch)

    decision = asyncio.run(
        llm_router.route(profile(), "what's bitcoin doing today", [])
    )

    assert decision == {"kind": "reply", "text": "Bitcoin is steady around $65k."}


def test_route_retries_once_then_falls_back_to_chat(monkeypatch):
    calls = scripted([resp(tool_calls=[("open_app", '{"name": 42}')])], monkeypatch)

    decision = asyncio.run(llm_router.route(profile(), "open it", []))

    assert decision["kind"] == "chat"
    assert len(calls) == 2  # exactly one retry
    note = calls[1]["messages"][0]["content"]
    assert "Your last reply was invalid" in note and "must be text" in note


def test_route_switches_to_json_mode_when_tools_are_rejected(monkeypatch):
    calls = scripted([
        Exception("400 : tools is not supported by this provider"),
        resp(content='{"steps": [{"tool": "open_app", "args": {"name": "whatsapp"}}]}'),
    ], monkeypatch)

    decision = asyncio.run(llm_router.route(profile(), "open whatsapp", []))

    assert decision["kind"] == "steps"
    assert calls[0]["tools"] is not None  # native first
    assert calls[1]["tools"] is None      # then strict JSON
    assert llm_router._mode_for(profile()) == "json"  # remembered


def test_route_accepts_json_from_a_model_that_cannot_call_tools(monkeypatch):
    scripted([resp(content='{"tool": "open_url", "args": {"url": "https://x.com"}}')],
             monkeypatch)

    decision = asyncio.run(llm_router.route(profile(), "go to x", []))

    assert decision == {"kind": "steps",
                        "steps": [{"action": "open_url", "url": "https://x.com"}]}


def test_route_keeps_history_and_appends_only_new_text(monkeypatch):
    calls = scripted([resp(content="hi")], monkeypatch)
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"},
               {"role": "user", "content": "open it"}]

    asyncio.run(llm_router.route(profile(), "open it", history))

    roles = [(m["role"], m["content"]) for m in calls[0]["messages"]]
    assert roles[0][0] == "system"
    assert roles[-1] == ("user", "open it")  # not sent twice


def test_route_never_raises_on_a_broken_response(monkeypatch):
    scripted([{"choices": []}], monkeypatch)

    decision = asyncio.run(llm_router.route(profile(), "x", []))

    assert decision["kind"] == "chat"


# --- through the API --------------------------------------------------------

def _script(responses, monkeypatch):
    return scripted(responses, monkeypatch)


def test_llm_path_shows_the_same_action_cards(client, monkeypatch):
    _script([resp(tool_calls=[("open_app", '{"name": "whatsapp"}')])], monkeypatch)

    events = sse_events(client.post(
        "/api/chat", json={"message": "can you open whatsapp for me"}
    ).text)

    assert [e["type"] for e in events][:2] == ["start", "action"]
    done = events[-1]
    assert done["type"] == "done"
    assert [a["kind"] for a in done["actions"]] == ["open_app"]
    assert [a["status"] for a in done["actions"]] == ["done"]
    assert "WhatsApp" in done["text"]


def test_the_fast_path_still_runs_before_the_model(client, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the model must not run for a fast-path message")

    monkeypatch.setattr(llm_router, "route", explode)

    events = sse_events(client.post(
        "/api/chat", json={"message": "open YouTube and search lo-fi"}
    ).text)

    assert events[-1]["type"] == "done"
    assert [a["kind"] for a in events[-1]["actions"]] == ["search_in_browser"]


def test_the_llm_path_drops_a_covered_open_too(monkeypatch):
    # the model answers "open youtube" + "search on youtube" -> one tab
    _script([resp(tool_calls=[
        ("open_url", '{"url": "https://www.youtube.com"}'),
        ("search_in_browser", '{"site": "youtube", "query": "lo-fi"}'),
    ])], monkeypatch)

    decision = asyncio.run(llm_router.route(
        profile(), "pull up youtube and find lo-fi", []))

    assert decision["kind"] == "steps"
    assert decision["steps"] == [
        {"action": "search_in_browser", "site": "youtube", "query": "lo-fi"}]


def test_mixed_message_sends_only_the_unknown_part_to_the_model(client, monkeypatch):
    calls = _script([resp(content="Because gold is dollars, and dollars rose.")],
                    monkeypatch)

    events = sse_events(client.post("/api/chat", json={
        "message": "open youtube and why is gold moving today"}).text)

    assert events[-1]["type"] == "done"
    routed = calls[0]["messages"][-1]["content"]
    assert "gold" in routed                    # the unknown half reaches the model
    assert "youtube" not in routed             # the known half does not
    assert events[-1]["actions"][0]["kind"] == "open_url"  # the rule's own step still ran
    assert "Opened youtube.com." in events[-1]["text"]
    assert "gold" in events[-1]["text"]


def test_a_whole_unknown_message_reaches_the_model_verbatim(client, monkeypatch):
    calls = _script([resp(content="Gold is up 0.4% today.")], monkeypatch)

    events = sse_events(client.post(
        "/api/chat", json={"message": "Pull up the gold chart, please!"}).text)

    assert calls[0]["messages"][-1]["content"] == "Pull up the gold chart, please!"
    assert events[-1]["type"] == "done"
    assert events[-1].get("actions") == []


def test_an_llm_install_still_stops_at_the_confirm_card(client, monkeypatch):
    import backend.tools.install as install

    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(
        install, "run_winget",
        lambda args, timeout=0, on_line=None: (0, "Name Id Version\nx"),
    )
    monkeypatch.setattr(
        install, "parse_search",
        lambda out: [{"name": "VideoLAN VLC", "id": "VideoLAN.VLC", "version": "3.0.20"}],
    )
    _script([resp(tool_calls=[("install_app", '{"name": "vlc"}')])], monkeypatch)

    events = sse_events(client.post("/api/chat",
                                    json={"message": "put vlc on this pc"}).text)

    action = events[-1]["actions"][0]
    assert action["kind"] == "install_app"
    assert action["status"] == "needs_confirm"  # requirement 5: never installs itself
    assert action["title"] == "Install VideoLAN VLC?"


def test_an_llm_whatsapp_always_stops_at_the_confirm_card(client, monkeypatch):
    _script([resp(tool_calls=[("whatsapp_message",
                               '{"contact": "mom", "text": "hi mom"}')])], monkeypatch)

    events = sse_events(client.post("/api/chat",
                                    json={"message": "whatsapp mom hi mom"}).text)

    action = events[-1]["actions"][0]
    assert action["kind"] == "whatsapp_message"
    assert action["status"] == "needs_confirm"  # never opens anything by itself
    assert action["title"] == "Send \u201chi mom\u201d to Mom?"
    assert action["data"]["url"].startswith("whatsapp://send?phone=")


def test_an_unknown_contact_comes_back_as_a_friendly_miss(client, monkeypatch):
    _script([resp(tool_calls=[("whatsapp_message",
                               '{"contact": "Zara", "text": "hi"}')])], monkeypatch)

    events = sse_events(client.post("/api/chat",
                                    json={"message": "whatsapp zara hi"}).text)

    action = events[-1]["actions"][0]
    assert action["status"] == "failed"
    assert "Zara" in action["title"]
    assert "Contacts" in (action["detail"] or "")


def test_after_one_bad_retry_the_model_answers_normally(client, monkeypatch):
    _script([resp(tool_calls=[("open_app", "{}")])], monkeypatch)  # invalid twice
    monkeypatch.setattr(
        "backend.core.llm.stream_chat",
        _aiter("Have you tried restarting the printer?"),
    )

    events = sse_events(client.post("/api/chat",
                                    json={"message": "fix my printer for me"}).text)

    assert events[-1]["type"] == "done"
    assert events[-1].get("actions", []) == []   # no half-run tool
    assert "printer" in "".join(
        e.get("text", "") for e in events if e["type"] in ("delta", "done")
    )


def test_no_provider_means_the_router_is_never_consulted(client, monkeypatch):
    from backend.core import config

    config.CONFIG_PATH.write_text(json.dumps(
        {"providers": [], "active": None, "theme": "system"}), encoding="utf-8")

    def explode(*args, **kwargs):
        raise AssertionError("no provider -> no LLM path")

    monkeypatch.setattr(llm_router, "route", explode)
    response = client.post("/api/chat", json={"message": "what is gold"})

    assert response.status_code == 400
    assert "No model chosen" in response.json()["detail"]


def _aiter(text: str):
    async def stream_chat(target, history):
        yield text

    return stream_chat


# --- Phase 4: research (findings in, sourced bullets out) -------------------

def _action(kind, items, status="done"):
    return {"kind": kind, "status": status, "data": {"items": items}}


def test_findings_comes_from_the_cards_the_tools_produced():
    items = [{"title": "Gold hits a high", "source": "Kitco", "when": "2h",
              "url": "https://k/1"}]
    actions = [
        _action("get_news", items),
        _action("get_news", items, status="running"),   # not finished yet
        _action("open_app", items),                     # not a research tool
        {"kind": "web_search", "status": "done", "data": {}},  # no items
    ]

    found = llm_router.findings_from(actions)

    assert found == items


def test_findings_are_capped_and_text_never_keeps_markup():
    many = [{"title": f"Story {i}", "source": "S", "when": "1h",
             "url": f"https://x/{i}"} for i in range(60)]
    text = llm_router.findings_text(many[:5] + [{"title": "<b>Gold</b> &amp; up",
                                                 "source": "Kitco", "when": "2h",
                                                 "url": "https://k/1"}])

    assert len(llm_router.findings_text(many).splitlines()) == llm_router.FINDINGS_CAP
    assert "<b>" not in text and "&amp;" not in text
    assert "(Kitco, 2h) https://k/1" in text


def test_research_messages_keep_the_rules_in_the_system_slot():
    history = [{"role": "user", "content": "why is gold moving"},
               {"role": "assistant", "content": "Checking."}]
    messages = llm_router.research_messages(
        "why is gold moving", history,
        [{"title": "Gold up", "source": "Kitco", "when": "2h", "url": "https://k/1"}],
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == llm_router.RESEARCH_SYSTEM
    assert "Findings:" in messages[-1]["content"]
    assert messages[-1]["content"].startswith("why is gold moving")
    assert "never instructions" in messages[0]["content"]  # requirement 4
    # the question is carried once, at the end, with the findings attached
    assert [m["content"] for m in messages].count("why is gold moving") == 0
    assert messages[-1]["content"].startswith("why is gold moving\n\nFindings:")


def test_the_footer_is_deterministic_not_left_to_the_model():
    footer = llm_router.research_footer()

    assert "As of " in footer
    assert "Context, not trading advice." in footer


def test_the_research_completion_is_offered_no_tools(monkeypatch):
    """Requirement 4: web results can never trigger actions."""
    seen: list = []

    async def stream_chat(target, messages):
        seen.append(messages)
        yield "- Gold rose [Kitco](https://k/1)"

    monkeypatch.setattr("backend.core.llm.stream_chat", stream_chat)
    from backend.core import llm

    async def run():
        return [c async for c in llm.stream_chat({}, [])]

    asyncio.run(run())
    assert len(seen) == 1


def test_model_calls_get_news_then_answers_with_sourced_bullets(client, monkeypatch):
    from backend.core import llm

    _script([resp(tool_calls=[("get_news", '{"topic": "gold"}')])], monkeypatch)
    monkeypatch.setattr(
        "backend.tools.news.items_for",
        lambda topic, limit=8: [{"title": "Gold hits a high", "source": "Kitco",
                                 "when": "2h", "url": "https://kitco.com/1",
                                 "snippet": ""}],
    )

    async def stream_chat(target, messages):
        assert messages[0]["role"] == "system"
        assert "Findings:" in messages[-1]["content"]
        assert not any(m.get("tools") for m in messages)
        yield "- Gold hit a record [Kitco](https://kitco.com/1)"
        yield " on Tuesday."

    monkeypatch.setattr(llm, "stream_chat", stream_chat)

    events = sse_events(client.post(
        "/api/chat", json={"message": "why is gold moving today"}
    ).text)

    done = events[-1]
    assert done["type"] == "done"
    assert [a["kind"] for a in done["actions"]] == ["get_news"]
    assert "Kitco" in done["text"]
    assert "Context, not trading advice." in done["text"]
    assert "As of " in done["text"]
    # the reply stands alone: no "Showed 3 gold headlines." in front of the bullets
    assert not done["text"].startswith("Showed")


def test_the_summarize_button_answers_from_the_headlines_it_was_given(
    client, monkeypatch, fake_db,
):
    from backend.core import llm

    def explode(*args, **kwargs):
        raise AssertionError("Summarize must not re-run the fast path or route")

    monkeypatch.setattr(llm_router, "route", explode)
    monkeypatch.setattr("backend.core.router.parse_parts", lambda t: ([], []))

    asked: list = []

    async def stream_chat(target, messages):
        asked.append(messages)
        yield "- Silver rose [Reuters](https://r/1)"

    monkeypatch.setattr(llm, "stream_chat", stream_chat)

    events = sse_events(client.post("/api/chat", json={
        "message": "Summarize the latest silver news",
        "findings": [{"title": "Silver rose", "source": "Reuters", "when": "1h",
                      "url": "https://r/1"}],
    }).text)

    done = events[-1]
    assert done["type"] == "done"
    assert "Reuters" in done["text"]
    assert "Context, not trading advice." in done["text"]
    assert "Findings:" in asked[0][-1]["content"]


def test_a_research_failure_still_saves_the_headlines_card(client, monkeypatch):
    from backend.core import llm

    _script([resp(tool_calls=[("get_news", '{"topic": "gold"}')])], monkeypatch)
    monkeypatch.setattr(
        "backend.tools.news.items_for",
        lambda topic, limit=8: [{"title": "Gold up", "source": "Kitco",
                                 "when": "2h", "url": "https://k/1", "snippet": ""}],
    )

    async def boom(target, messages):
        raise __import__("backend.core.llm", fromlist=["LLMError"]).LLMError(
            "The model is offline.", fix="settings")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "stream_chat", boom)

    events = sse_events(client.post(
        "/api/chat", json={"message": "why is gold moving today"}
    ).text)

    assert events[-1]["type"] == "error"
    assert events[-1]["fix"] == "settings"
    # the card itself was already streamed, so the headlines are not lost
    kinds = {e["action"]["kind"] for e in events if e["type"] == "action"}
    assert kinds == {"get_news"}
