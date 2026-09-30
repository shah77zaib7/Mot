"""play_youtube — find the first video with yt-dlp and open its watch page.

Metadata only: `yt-dlp ytsearch1:` with --skip-download, no API key. If the
lookup fails we open the YouTube search page instead and say so.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import quote_plus

from ..core import apps
from . import launch
from .registry import register

SEARCH_URL = "https://www.youtube.com/results?search_query={q}"
WATCH_URL = "https://www.youtube.com/watch?v={id}"
LOOKUP_TIMEOUT = 25.0
_VIDEO_ID = re.compile(r"^[\w-]{6,20}$")


def ytdlp_command() -> list[str] | None:
    """How to call yt-dlp here: the exe on PATH, or the Python module."""
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import importlib.util

        if importlib.util.find_spec("yt_dlp") is not None:
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:  # noqa: BLE001 - a broken install just means "not available"
        return None
    return None


def run_ytdlp(args: list[str], timeout: float = LOOKUP_TIMEOUT) -> tuple[int, str]:
    """Run yt-dlp once. Tests replace this whole function."""
    cmd = ytdlp_command()
    if cmd is None:
        return 127, "yt-dlp is not installed."
    kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":  # never flash a console window
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    try:
        proc = subprocess.run([*cmd, *args], timeout=timeout, **kwargs)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return 1, "yt-dlp failed to run."
    return proc.returncode, proc.stdout or ""


def find_video(query: str) -> dict[str, str] | None:
    """First hit of `ytsearch1:<query>` -> {"id", "title"} or None."""
    code, out = run_ytdlp([
        "--skip-download", "--no-warnings", "--flat-playlist",
        "--playlist-items", "1", "--print", "%(id)s\t%(title)s",
        f"ytsearch1:{query}",
    ])
    if code != 0:
        return None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        video_id, _, title = line.partition("\t")
        if _VIDEO_ID.match(video_id):
            return {"id": video_id, "title": title.strip() or query}
    return None


def _open(url: str) -> dict[str, Any]:
    return launch.open_url(url, browser=apps.browser())


@register(
    "play_youtube",
    "Play a YouTube video: give what to play, Mot finds the first match and "
    "opens it (falls back to the search page when nothing is found).",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to play, e.g. dilbar dilbar"}
        },
        "required": ["query"],
    },
)
def play_youtube(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "message": "There is nothing to play.", "data": {}}

    video = find_video(query)
    if video is not None:
        url = WATCH_URL.format(id=video["id"])
        result = _open(url)
        if result.get("ok"):
            return {
                "ok": True,
                "message": f"Playing “{video['title']}”",
                "data": {"url": url, "video_id": video["id"], "title": video["title"],
                         "query": query},
            }

    url = SEARCH_URL.format(q=quote_plus(query))
    result = _open(url)
    if result.get("ok"):
        return {
            "ok": True,
            "message": "Couldn\u2019t find the video, so I opened the YouTube search instead.",
            "data": {"url": url, "query": query, "fallback": True},
        }
    return {
        "ok": False,
        "message": "Couldn\u2019t open YouTube. Check your browser preference in Settings.",
        "data": {"query": query},
    }
