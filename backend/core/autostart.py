"""Start Mot when Windows signs in — the per-user Run key, nothing else.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run needs no administrator
rights, is read by Explorer at logon, and is the only registry key Mot ever
touches. The value runs pythonw.exe on run.pyw with --background, so Mot comes
up hidden in the tray instead of popping a window at you.

`_reg()` returns the winreg module; tests hand it a fake instead.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger("mot")

ROOT = paths.program_root()
KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Mot"


def _reg() -> Any:
    import winreg

    return winreg


def interpreter() -> Path:
    """pythonw.exe — no console window, next to whichever python is running."""
    exe = Path(sys.executable)
    sibling = exe.with_name("pythonw.exe")
    return sibling if sibling.is_file() else exe


def command() -> str:
    """Exactly what goes into the Run value."""
    return f'"{interpreter()}" "{ROOT / "run.pyw"}" --background'


def enabled() -> bool:
    """Is Mot in the startup list right now? The registry is the truth."""
    reg = _reg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, KEY_PATH, 0, reg.KEY_READ) as key:
            value, _kind = reg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return bool(str(value).strip())


def set_enabled(on: bool) -> None:
    """Add or remove the startup entry. Raises RuntimeError when refused."""
    reg = _reg()
    if not on:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, KEY_PATH, 0,
                             reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, VALUE_NAME)
        except OSError:
            return  # already off: nothing to remove
        log.info("auto-start off: Run key removed")
        return
    try:
        with reg.CreateKey(reg.HKEY_CURRENT_USER, KEY_PATH) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command())
    except OSError as exc:
        raise RuntimeError(
            "Windows would not save the startup entry. "
            f"The reason was: {exc}") from exc
    log.info("auto-start on: %s", command())
