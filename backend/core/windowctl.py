"""Show, hide and close the Mot window — every caller goes through here.

The tray icon, the global hotkey, a second launch and the title bar's X all
end up in this one module, so "where is the window right now" has exactly one
answer.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from typing import Any

log = logging.getLogger("mot")

TRAY_TEXT = (
    "Mot is still running.\n\n"
    "It is in the notification area next to the clock - click its icon to "
    "bring the window back. Choose \"Quit Mot\" in that menu to close Mot "
    "for good."
)

_window: Any = None
_hidden = False       # a close went to the tray instead of ending the process
_minimized = False    # the user minimised it
_quitting = False     # Quit was asked: let the next close really close
_shown = threading.Event()


# -- lifecycle ---------------------------------------------------------------

def attach(window: Any, hidden: bool = False) -> None:
    """Take ownership of a freshly created pywebview window."""
    global _window, _hidden, _minimized, _quitting
    _window = window
    _hidden = bool(hidden)
    _minimized = False
    _quitting = False
    _shown.clear()
    try:
        window.events.shown += _on_shown
        window.events.minimized += _on_minimized
        window.events.restored += _on_restored
    except Exception:  # noqa: BLE001 - a missing event must not stop the app
        log.warning("window events could not be hooked", exc_info=True)


def detach() -> None:
    """Forget the window (shutdown, tests)."""
    global _window, _hidden, _minimized, _quitting
    _window = None
    _hidden = False
    _minimized = False
    _quitting = False
    _shown.clear()


def _on_shown() -> None:
    _shown.set()


def _on_minimized() -> None:
    global _minimized
    _minimized = True


def _on_restored() -> None:
    global _minimized
    _minimized = False


def is_hidden() -> bool:
    return _hidden


def is_shown() -> bool:
    return _shown.is_set()


# -- moving the window around ------------------------------------------------

def _call(window: Any, name: str, *args: Any) -> None:
    try:
        getattr(window, name)(*args)
    except Exception:  # noqa: BLE001 - a dying window must not raise here
        log.warning("window.%s() failed", name, exc_info=True)


def show() -> None:
    """Bring Mot to the front (creating nothing, just revealing)."""
    global _hidden, _minimized
    window = _window
    if window is None:
        return
    if _minimized:
        _call(window, "restore")
    _call(window, "show")
    _hidden = False
    _minimized = False


def hide() -> None:
    """Send Mot to the tray without ending anything."""
    global _hidden
    window = _window
    if window is None:
        return
    _call(window, "hide")
    _hidden = True


def toggle() -> None:
    """The global hotkey: show a window that is away, hide one that is here."""
    if _window is None:
        return
    if _hidden or _minimized:
        show()
    else:
        hide()


def quit() -> None:
    """Tray > Quit Mot: really close, whatever "When I close the window" says."""
    global _quitting
    _quitting = True
    window = _window
    if window is None:
        return

    def work() -> None:
        time.sleep(0.05)  # let the tray menu callback finish first
        _call(window, "destroy")

    threading.Thread(target=work, name="mot-quit", daemon=True).start()


# -- the title bar's X -------------------------------------------------------

def on_closing(window: Any = None) -> bool:  # noqa: ARG001 - pywebview passes it
    """pywebview `closing` handler. Returning False cancels the close."""
    if _quitting:
        return True
    if not _close_to_tray():
        return True
    # Leave the real work to another thread: pywebview's hide() marshals to the
    # GUI thread, and we are standing on it right now.
    threading.Thread(target=_to_tray, name="mot-to-tray", daemon=True).start()
    return False


def _to_tray() -> None:
    time.sleep(0.05)  # let the FormClosing handler finish cancelling first
    hide()
    notice_once()


def _close_to_tray() -> bool:
    try:
        from . import config

        return bool(config.general()["close_to_tray"])
    except Exception:  # noqa: BLE001 - no readable setting: keep the default
        return True


def notice_once() -> None:
    """The first close that only hides Mot says where the window went."""
    try:
        from . import config

        if config.general()["tray_notice_shown"]:
            return
        config.set_general({"tray_notice_shown": True})
    except Exception:  # noqa: BLE001 - never fail a close over the notice
        log.warning("could not record the tray notice", exc_info=True)
        return
    message_box(TRAY_TEXT)


def message_box(text: str) -> None:
    """A native box, on its own thread, so the app never blocks behind it."""
    try:
        ctypes.windll.user32.MessageBoxW(None, text, "Mot", 0x40)  # MB_ICONINFORMATION
    except Exception:  # noqa: BLE001 - the notice is a nicety, not a duty
        log.warning("the tray notice could not be shown", exc_info=True)
