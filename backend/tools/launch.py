"""Where Mot actually starts things — browsers and installed apps.

Thin, replaceable launchers: tests swap these out so no test opens a real app.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from typing import Any

# Preferred browser -> known install locations (first hit wins).
BROWSER_PATHS: dict[str, list[str]] = {
    "chrome": [
        r"%ProgramFiles%\Google\Chrome\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    ],
    "brave": [
        r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
}


def _spawn(args: list[str]) -> None:
    """Start a process detached from Mot's own console."""
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    subprocess.Popen(args, **kwargs)  # noqa: S603 - fixed argv, never user shell


def browser_exe(kind: str) -> str | None:
    """Absolute path of a preferred browser, or None when it isn't installed."""
    for raw in BROWSER_PATHS.get(kind, []):
        path = os.path.expandvars(raw)
        if os.path.exists(path):
            return path
    return None


def open_url(url: str, browser: str = "default") -> dict[str, Any]:
    """Open a URL. `browser` is "default" or chrome/brave/edge."""
    kind = (browser or "default").lower()
    if kind in ("default", ""):
        os.startfile(url)  # noqa: S606 - Windows default handler
        return {"ok": True, "browser": "default"}
    exe = browser_exe(kind)
    if exe:
        _spawn([exe, url])
        return {"ok": True, "browser": kind}
    os.startfile(url)  # preferred browser missing: fall back, caller tells the user
    return {"ok": True, "browser": "default", "fallback": kind}


def open_scheme(url: str) -> dict[str, Any]:
    """Open a custom protocol link (whatsapp://send?...).

    Windows raises OSError when no app is registered for the scheme — the
    caller then falls back to a normal https link.
    """
    try:
        os.startfile(url)  # noqa: S606 - Windows default handler
    except OSError:
        return {"ok": False, "message": "Windows has no app for that kind of link."}
    return {"ok": True, "handler": "scheme"}


def launch_app(entry: dict[str, Any]) -> dict[str, Any]:
    """Start a discovered app: an .exe target or a UWP AppID."""
    target = (entry.get("target") or "").strip()
    if not target:
        return {"ok": False, "message": "That app has no target to launch."}
    if entry.get("kind") == "uwp":
        _spawn(["explorer.exe", f"shell:AppsFolder\\{target}"])
        return {"ok": True}
    args = shlex.split(entry.get("args") or "", posix=False)
    _spawn([target, *args])
    return {"ok": True}
