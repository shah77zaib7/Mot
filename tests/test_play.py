"""play_youtube — the yt-dlp lookup is faked, so nothing here opens a video."""
from __future__ import annotations

import pytest

from backend.core import apps
from backend.tools import launch, play, registry

FAKE_APPS = [
    {"name": "Google Chrome", "kind": "app", "target": r"C:\chrome.exe", "args": ""},
]


@pytest.fixture(autouse=True)
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {}, "apps": FAKE_APPS})
    yield


@pytest.fixture
def opened(monkeypatch):
    """Record every URL the tool would have opened."""
    urls: list[str] = []
    monkeypatch.setattr(
        launch, "open_url",
        lambda url, browser="default": urls.append(url) or {"ok": True},
    )
    return urls


@pytest.fixture
def fake_ytdlp(monkeypatch):
    """Fake yt-dlp: (returncode, output) per call, with the args it was given."""
    seen: list[list[str]] = []
    script: list[tuple[int, str]] = []

    def run(args, timeout=0.0):
        seen.append(list(args))
        return script[min(len(seen) - 1, len(script) - 1)]

    monkeypatch.setattr(play, "run_ytdlp", run)
    return {"seen": seen, "script": script}


# --- the lookup -------------------------------------------------------------

def test_run_ytdlp_calls_the_binary_with_a_timeout(monkeypatch):
    seen: dict = {}

    class Proc:
        returncode = 0
        stdout = "ok\n"

    def fake_run(cmd, timeout=0.0, **kwargs):
        seen.update(cmd=cmd, timeout=timeout, kwargs=kwargs)
        return Proc()

    monkeypatch.setattr(play, "ytdlp_command", lambda: ["yt-dlp.exe"])
    monkeypatch.setattr(play.subprocess, "run", fake_run)

    code, out = play.run_ytdlp(["--version"])

    assert (code, out) == (0, "ok\n")
    assert seen["cmd"] == ["yt-dlp.exe", "--version"]
    assert seen["timeout"] == play.LOOKUP_TIMEOUT
    assert "creationflags" in seen["kwargs"]  # no console window on Windows


def test_a_missing_ytdlp_is_a_soft_failure(monkeypatch):
    monkeypatch.setattr(play, "ytdlp_command", lambda: None)

    code, out = play.run_ytdlp(["--version"])

    assert code == 127 and "not installed" in out


def test_find_video_reads_the_first_hit(fake_ytdlp):
    fake_ytdlp["script"].append(
        (0, "dQw4w9WgXcQ\tNever Gonna Give You Up\n")
    )

    video = play.find_video("rick roll")

    assert video == {"id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up"}
    assert fake_ytdlp["seen"][0][-1] == "ytsearch1:rick roll"
    assert "--skip-download" in fake_ytdlp["seen"][0]  # metadata only


def test_find_video_returns_none_on_a_failed_lookup(fake_ytdlp):
    fake_ytdlp["script"].append((1, "ERROR: Unable to extract"))

    assert play.find_video("nothing here") is None


def test_find_video_ignores_junk_output(fake_ytdlp):
    fake_ytdlp["script"].append((0, "WARNING: x\nnot a video line\n"))

    assert play.find_video("x") is None


# --- the tool ---------------------------------------------------------------

def test_play_opens_the_watch_page(opened, monkeypatch):
    monkeypatch.setattr(play, "find_video",
                        lambda q: {"id": "abc123def4", "title": "Dilbar"})

    result = registry.call("play_youtube", {"query": "dilbar dilbar"})

    assert result["ok"] is True
    assert opened == ["https://www.youtube.com/watch?v=abc123def4"]
    assert "Dilbar" in result["message"]
    assert result["data"]["video_id"] == "abc123def4"


def test_play_falls_back_to_the_search_page_and_says_so(opened, monkeypatch):
    monkeypatch.setattr(play, "find_video", lambda q: None)

    result = registry.call("play_youtube", {"query": "dilbar dilbar"})

    assert result["ok"] is True
    assert opened == ["https://www.youtube.com/results?search_query=dilbar+dilbar"]
    assert result["data"]["fallback"] is True
    assert "search instead" in result["message"]


def test_play_without_a_query_fails_friendly(opened):
    result = registry.call("play_youtube", {"query": "   "})

    assert result["ok"] is False
    assert opened == []


def test_the_play_step_is_registered_for_the_llm():
    from backend.tools import registry as reg

    tool = reg.get("play_youtube")

    assert tool is not None
    assert tool.schema["required"] == ["query"]
