"""Phase 6: every LLM call has a real timeout, and failures classify cleanly."""
from __future__ import annotations

import asyncio

import pytest

from backend.core import fallback, llm

LOCAL = {"name": "Mock", "model": "openai/mock", "api_base": "http://127.0.0.1:9/v1"}
REMOTE = {"name": "Cloud", "model": "openai/x", "api_base": "https://api.example.com/v1"}


async def _drain(profile) -> None:
    async for _ in llm.stream_chat(profile, [{"role": "user", "content": "hi"}]):
        pass


def test_the_timeout_is_at_least_ten_seconds():
    assert llm.timeout() >= 10.0
    assert llm.REQUEST_TIMEOUT >= 10.0
    assert llm.timeout() >= llm.MIN_TIMEOUT


def test_a_hung_model_call_is_cut_off_and_called_a_timeout(monkeypatch):
    monkeypatch.setattr(llm, "REQUEST_TIMEOUT", 0.05)
    monkeypatch.setattr(llm, "MIN_TIMEOUT", 0.02)

    class Hung:
        async def acompletion(self, **kwargs):  # noqa: ANN001, ARG001
            await asyncio.sleep(30)

    async def no_probe(profile):  # noqa: ANN001, ARG001
        return None

    monkeypatch.setattr(llm, "_litellm", lambda: Hung())
    monkeypatch.setattr(llm, "probe_reachable", no_probe)

    with pytest.raises(llm.LLMError) as exc:
        asyncio.run(_drain(LOCAL))

    assert exc.value.kind == "timeout"


@pytest.mark.parametrize(
    "exc,kind",
    [
        (TimeoutError(), "timeout"),
        (Exception("Read timed out waiting for response"), "timeout"),
        (Exception("429 Too Many Requests"), "rate_limit"),
        (Exception("You exceeded your current quota"), "rate_limit"),
        (Exception("Service Unavailable"), "server"),
        (Exception("bad gateway from upstream"), "server"),
        (Exception("401 unauthorized"), "key_invalid"),
        (Exception("model_not_found: no such model"), "not_found"),
        (Exception("connection refused"), None),  # never a switch
        (Exception("could not resolve host"), None),
    ],
)
def test_friendly_tags_each_failure_for_the_fallback(exc, kind):
    err = llm.friendly(exc, REMOTE)

    assert err.kind == kind


def test_an_http_status_beats_the_wording(monkeypatch):
    class Boom(Exception):
        status_code = 503

    assert llm.friendly(Boom("weird message"), REMOTE).kind == "server"


def test_an_unknown_error_is_never_switched_away_from():
    err = llm.friendly(Exception("something odd happened"), REMOTE)

    assert err.kind is None
    assert fallback.classify(err) is None


@pytest.mark.parametrize("kind", ["rate_limit", "timeout", "server", "not_found"])
def test_classified_failures_have_a_cooldown(kind):
    assert fallback.classify(llm.LLMError("x", kind=kind)) == kind


def test_key_invalid_is_switchable_but_has_no_rest():
    assert fallback.COOLDOWN["key_invalid"] == 0
