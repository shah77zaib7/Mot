"""llm.py: the reachability probe that gates every model call."""
from __future__ import annotations

import asyncio

from backend.core import llm


class _Writer:
    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def test_probe_retries_a_dropped_connection(monkeypatch):
    attempts: list[str] = []

    async def flaky(host, port, *args, **kwargs):
        attempts.append(host)
        if len(attempts) == 1:
            raise ConnectionResetError("dropped")
        return None, _Writer()

    monkeypatch.setattr(asyncio, "open_connection", flaky)

    error = asyncio.run(llm.probe_reachable(
        {"name": "opencode", "api_base": "https://opencode.ai/zen/v1"}))

    assert error is None
    assert len(attempts) == 2  # the retry is what saves the reply


def test_a_local_server_that_is_down_fails_in_one_try(monkeypatch):
    attempts: list[str] = []

    async def refused(host, port, *args, **kwargs):
        attempts.append(host)
        raise ConnectionRefusedError()

    monkeypatch.setattr(asyncio, "open_connection", refused)

    error = asyncio.run(llm.probe_reachable(
        {"name": "Local Ollama", "api_base": "http://localhost:11434"}))

    assert error is not None
    assert "isn't reachable" in error.message
    assert len(attempts) == 1  # local keeps failing fast


def test_probe_skips_an_empty_base():
    assert asyncio.run(llm.probe_reachable({"name": "x", "api_base": None})) is None
