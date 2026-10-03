"""Phase 6: the ordered fallback list, cooldowns and cost safety.

Every model here is a fake one in a throwaway config.json, and the keyring is
a plain dict — no real provider, key or saved setting is ever touched.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.core import config, fallback, llm, llm_router


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A throwaway config.json and a fake keyring — never the real ones."""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    store: dict[str, str] = {}
    monkeypatch.setattr(config, "set_secret", lambda ref, value: store.__setitem__(ref, value))
    monkeypatch.setattr(config, "get_secret", lambda ref: store.get(ref))
    monkeypatch.setattr(config, "delete_secret", lambda ref: store.pop(ref, None))
    config.CONFIG_PATH.write_text(
        json.dumps({"theme": "system", "active": None, "providers": []}),
        encoding="utf-8",
    )
    fallback.clear()
    yield store
    fallback.clear()


def add_model(vault, name: str, model_id: str, tag: str = "free") -> dict:
    """One provider with one model, on a local-looking host (no key needed)."""
    return config.save_provider({
        "name": name,
        "base_url": "http://127.0.0.1:9/v1",
        "models": [{"id": model_id, "tag": tag, "tag_locked": True}],
    })


def script(monkeypatch, failures: dict, decision=None) -> list[str]:
    """Replace llm_router.route: labels in `failures` raise with that kind."""
    calls: list[str] = []

    async def fake_route(profile, text, history, done=None):
        calls.append(profile["label"])
        kind = failures.get(profile["label"])
        if kind:
            raise llm.LLMError("provider said no", code=kind, kind=kind)
        return decision or {"kind": "reply", "text": f"hello from {profile['label']}"}

    monkeypatch.setattr(llm_router, "route", fake_route)
    return calls


def chain(target):
    return asyncio.run(fallback.route(fallback.candidates(target), "hi", []))


# --- ordering ---------------------------------------------------------------

def test_candidates_walk_the_saved_list_in_order(vault):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))

    assert [p["label"] for p in fallback.candidates(target)] == ["model-a", "model-b"]


def _ids(model_id: str) -> tuple[str, str]:
    for provider in config.load()["providers"]:
        if any(m["id"] == model_id for m in provider["models"]):
            return provider["id"], model_id
    raise AssertionError(model_id)


def test_reordering_is_saved_and_unknown_rows_are_dropped(vault):
    a = add_model(vault, "Mock A", "model-a")
    b = add_model(vault, "Mock B", "model-b")

    saved = config.set_fallback([
        {"provider_id": b["id"], "model_id": "model-b", "auto": False},
        {"provider_id": a["id"], "model_id": "model-a", "auto": True},
        {"provider_id": "p-ghost", "model_id": "nope", "auto": True},
        {"provider_id": a["id"], "model_id": "model-a", "auto": True},  # duplicate
    ])

    assert [(e["model_id"], e["auto"]) for e in saved] == [
        ("model-b", False),
        ("model-a", True),
    ]


def test_the_order_decides_who_is_tried_after_the_requested_model(vault):
    add_model(vault, "Mock A", "model-a")
    b = add_model(vault, "Mock B", "model-b")
    c = add_model(vault, "Mock C", "model-c")
    config.set_fallback([
        {"provider_id": c["id"], "model_id": "model-c", "auto": True},
        {"provider_id": b["id"], "model_id": "model-b", "auto": True},
    ])
    target = config.chat_target(*_ids("model-a"))

    # the requested model still goes first; the list orders what follows it
    assert [p["label"] for p in fallback.candidates(target)] == [
        "model-a", "model-c", "model-b",
    ]


# --- cost safety ------------------------------------------------------------

def test_a_paid_model_is_never_switched_into_unless_ticked(vault):
    add_model(vault, "Mock A", "model-a", tag="free")
    add_model(vault, "Mock B", "model-b", tag="paid")
    target = config.chat_target(*_ids("model-a"))

    assert [p["label"] for p in fallback.candidates(target)] == ["model-a"]

    entries = config.fallback_list()
    assert entries[1]["auto"] is False  # paid: off until the user ticks it

    config.set_fallback([{**e, "auto": True} for e in entries])
    assert [p["label"] for p in fallback.candidates(target)] == ["model-a", "model-b"]


def test_free_models_are_ticked_by_default(vault):
    add_model(vault, "Mock A", "model-a", tag="free")
    assert [e["auto"] for e in config.fallback_list()] == [True]


# --- switching --------------------------------------------------------------

def test_a_rate_limit_moves_on_and_cools_the_failed_model(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    calls = script(monkeypatch, {"model-a": "rate_limit"})

    out = chain(target)

    assert calls == ["model-a", "model-b"]
    assert out["profile"]["label"] == "model-b"
    assert out["notices"] == ["model-a hit its limit, switched to model-b"]

    resting = fallback.resting()
    assert [r["model_id"] for r in resting] == ["model-a"]
    assert resting[0]["reason"] == "rate limit"
    assert 250 <= resting[0]["seconds"] <= 300
    # the next request never even tries the resting one
    assert [p["label"] for p in fallback.candidates(target)] == ["model-b"]


def test_a_switch_also_moves_the_selected_model(vault, monkeypatch):
    """The picker must agree with the reply: after "switched to model-b",
    Settings and the model selector have to show model-b — otherwise the next
    refresh of GET /api/providers puts model-a back on screen."""
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": "rate_limit"})

    out = chain(target)

    assert out["profile"]["label"] == "model-b"
    active = config.active_model()
    assert (active["provider_id"], active["model_id"]) == _ids("model-b")


def test_a_failed_save_never_costs_us_the_reply(vault, monkeypatch):
    """A config write that refuses must not turn a working reply into an error."""
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": "rate_limit"})

    def refuse(provider_id, model_id):
        raise OSError("config is read-only")

    monkeypatch.setattr(config, "set_active", refuse)

    out = chain(target)

    assert out["profile"]["label"] == "model-b"
    assert out["notices"] == ["model-a hit its limit, switched to model-b"]


def test_key_invalid_switches_without_starting_a_cooldown(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": "key_invalid"})

    out = chain(target)

    assert out["profile"]["label"] == "model-b"
    assert out["notices"] == ["model-a has an invalid key, switched to model-b"]
    assert fallback.resting() == []  # the key may be fixed a second later


def test_only_the_listed_failures_may_switch_away(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    calls = script(monkeypatch, {"model-a": None})  # kind=None: not switchable

    async def fake_route(profile, text, history, done=None):
        calls.append(profile["label"])
        raise llm.LLMError("Local Ollama isn't reachable. Is it running?",
                           fix="settings", kind=None)

    monkeypatch.setattr(llm_router, "route", fake_route)

    with pytest.raises(llm.LLMError) as exc:
        chain(target)

    assert exc.value.kind is None
    assert calls == ["model-a"]  # stopped dead: no second model was burned
    assert fallback.resting() == []


@pytest.mark.parametrize(
    "kind,low,high",
    [("rate_limit", 290, 300), ("timeout", 1790, 1800),
     ("server", 1790, 1800), ("not_found", 21500, 21600)],
)
def test_each_failure_rests_for_its_own_length(vault, monkeypatch, kind, low, high):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": kind})

    chain(target)

    assert low <= fallback.resting()[0]["seconds"] <= high


def test_one_pass_and_then_a_friendly_list_of_what_failed(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    calls = script(monkeypatch, {"model-a": "rate_limit", "model-b": "server"})

    with pytest.raises(llm.LLMError) as exc:
        chain(target)

    assert calls == ["model-a", "model-b"]  # exactly one pass — never a loop
    err = exc.value
    assert err.code == "fallback_exhausted"
    assert err.models == [
        {"label": "model-a", "why": "rate limit"},
        {"label": "model-b", "why": "server error"},
    ]
    assert "Press Retry" in err.message
    assert "Settings > Models" in err.message


def test_hand_picking_a_resting_model_wakes_it_up(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": "server"})

    chain(target)
    assert fallback.resting()

    assert fallback.wake(*_ids("model-a")) is True
    assert fallback.resting() == []
    assert [p["label"] for p in fallback.candidates(target)] == ["model-a", "model-b"]


def test_a_cooldown_expires_on_its_own(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))
    script(monkeypatch, {"model-a": "rate_limit"})

    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(fallback.time, "time", lambda: clock["now"])

    chain(target)
    assert [r["model_id"] for r in fallback.resting()] == ["model-a"]

    clock["now"] += 301  # five minutes are up
    assert fallback.resting() == []
    assert [p["label"] for p in fallback.candidates(target)] == ["model-a", "model-b"]


def test_a_new_run_starts_with_every_model_ready(vault, monkeypatch):
    """Cooling lives in memory: closing Mot clears it, nothing is persisted."""
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    script(monkeypatch, {"model-a": "not_found"})
    chain(config.chat_target(*_ids("model-a")))
    assert fallback.resting()

    fallback.clear()

    assert fallback.resting() == []
    saved = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "cooldowns" not in saved and "resting" not in saved


# --- the streaming path -----------------------------------------------------

async def _drain(profiles, messages=None):
    return [event async for event in fallback.stream(profiles, messages or [])]


def test_stream_switches_before_a_word_is_shown(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))

    async def fake_stream(profile, messages):
        if profile["label"] == "model-a":
            raise llm.LLMError("rate limited", kind="rate_limit")
        for chunk in ("hello", " world"):
            yield chunk

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    events = asyncio.run(_drain(fallback.candidates(target)))

    assert events == [
        ("notice", "model-a hit its limit, switched to model-b"),
        ("delta", "hello"),
        ("delta", " world"),
    ]


def test_stream_never_switches_once_text_is_on_screen(vault, monkeypatch):
    add_model(vault, "Mock A", "model-a")
    add_model(vault, "Mock B", "model-b")
    target = config.chat_target(*_ids("model-a"))

    async def fake_stream(profile, messages):
        if profile["label"] == "model-a":
            yield "partial"
            raise llm.LLMError("died mid-reply", kind="server")
        yield "other"

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    seen: list[tuple[str, str]] = []

    async def run():
        async for event in fallback.stream(fallback.candidates(target), []):
            seen.append(event)

    with pytest.raises(llm.LLMError):
        asyncio.run(run())
    assert seen == [("delta", "partial")]  # no notice, no second model
