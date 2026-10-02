"""Is the Microsoft Edge WebView2 Runtime installed?

pywebview cannot make a window without it, and its own failure is a raw
HRESULT nobody can act on. Mot checks first and says, in plain English, what
to install and where. Nothing here writes to the registry or changes the
machine — it only looks.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

log = logging.getLogger("mot")

DOWNLOAD_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2/"

# The Evergreen Runtime ships its version under this client id (both 64- and
# 32-bit views of the registry).
CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
REG_PATH = r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
REG_PATH_32 = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"

USER_BASE = Path(os.environ.get("LOCALAPPDATA") or
                 str(Path.home() / "AppData" / "Local"))
MACHINE_BASES = (
    Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"),
    Path(os.environ.get("ProgramFiles") or r"C:\Program Files"),
)


def _folder_hit(base: Path) -> bool:
    """.../Microsoft/EdgeWebView/Application/<version>/EBWebView exists?"""
    try:
        app = base / "Microsoft" / "EdgeWebView" / "Application"
        return app.is_dir() and any(app.glob("*/EBWebView"))
    except OSError:
        return False


def _reg_hits() -> list[str]:
    """Versions reported by the Edge updater, for both registry views."""
    try:
        import winreg
    except ImportError:  # pragma: no cover - not on Windows
        return []
    found: list[str] = []
    views = [(winreg.KEY_WOW64_64KEY, REG_PATH), (winreg.KEY_WOW64_32KEY, REG_PATH_32)]
    for view, path in views:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            try:
                value, _ = winreg.QueryValueEx(key, CLIENT_ID)
            except OSError:
                value = None
            finally:
                winreg.CloseKey(key)
            if value and str(value) not in ("", "0.0.0.0"):
                found.append(str(value))
    return found


def installed() -> bool:
    """True when a usable WebView2 Runtime is on this machine."""
    if _folder_hit(USER_BASE):
        return True
    if any(_folder_hit(base) for base in MACHINE_BASES):
        return True
    return bool(_reg_hits())


def missing_message(check: Callable[[], bool] | None = None) -> str | None:
    """`None` when Mot can open its window, otherwise the sentence to show."""
    try:
        present = installed() if check is None else check()
    except Exception:  # noqa: BLE001 - a probe that explodes must not block Mot
        log.warning("WebView2 check failed, assuming it is installed",
                    exc_info=True)
        return None
    if present:
        return None
    return (
        "Mot needs the free Microsoft Edge WebView2 Runtime to show its "
        "window, and it is not installed.\n\n"
        "Download it here:\n"
        f"    {DOWNLOAD_URL}\n\n"
        "Install it, then start Mot again. Your data is untouched."
    )
