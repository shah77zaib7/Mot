"""The notification-area icon: pystray + Pillow, both imported lazily.

Menu: Open Mot (also the left-click), Refresh news now, Quit Mot.
Nothing here touches the window directly — the callbacks come from main().
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from . import paths

log = logging.getLogger("mot")

ICON_PATH = paths.icon_path()

_icon: Any = None
_thread: threading.Thread | None = None


def _pystray() -> Any:
    import pystray  # lazy: costs ~180 ms, and only when the tray is wanted

    return pystray


def _image() -> Any:
    from PIL import Image  # lazy: costs ~130 ms

    return Image.open(ICON_PATH)


def start(
    on_open: Callable[[], None],
    on_refresh: Callable[[], None],
    on_quit: Callable[[], None],
) -> bool:
    """Show the tray icon. Returns False when pystray/the icon is unavailable."""
    global _icon, _thread
    if _icon is not None:
        return True
    try:
        module = _pystray()
        image = _image()
    except Exception:  # noqa: BLE001 - a missing tray never stops the app
        log.warning("the tray icon is not available", exc_info=True)
        return False

    def open_mot(_icon: Any) -> None:
        on_open()

    def refresh(_icon: Any) -> None:
        on_refresh()

    def quit_mot(_icon: Any) -> None:
        on_quit()

    menu = module.Menu(
        module.MenuItem("Open Mot", open_mot, default=True),  # left-click
        module.MenuItem("Refresh news now", refresh),
        module.Menu.SEPARATOR,
        module.MenuItem("Quit Mot", quit_mot),
    )
    try:
        _icon = module.Icon("mot", image, "Mot - personal AI agent", menu)
    except Exception:  # noqa: BLE001
        log.warning("the tray icon could not be created", exc_info=True)
        return False
    _thread = threading.Thread(target=_run, name="mot-tray", daemon=True)
    _thread.start()
    return True


def _run() -> None:
    icon = _icon
    try:
        icon.run()
    except Exception:  # noqa: BLE001
        log.warning("the tray icon stopped early", exc_info=True)
        _release_setup(icon)


def _release_setup(icon: Any) -> None:
    """pystray's setup thread blocks on a private queue - never leave it stuck,
    or the process could not exit."""
    queue = getattr(icon, "_Icon__queue", None)
    if queue is None:
        return
    try:
        queue.put(True)
    except Exception:  # noqa: BLE001
        pass


def stop() -> None:
    """Remove the icon and let its threads finish (quit, tests)."""
    global _icon, _thread
    icon, _icon = _icon, None
    thread, _thread = _thread, None
    if icon is None:
        return
    try:
        icon.stop()
    except Exception:  # noqa: BLE001
        log.warning("the tray icon could not be stopped cleanly", exc_info=True)
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=3.0)


def notify(message: str, title: str = "Mot") -> None:
    """A small Windows balloon (used by "Refresh news now")."""
    icon = _icon
    if icon is None:
        return
    try:
        icon.notify(message, title)
    except Exception:  # noqa: BLE001 - a notification is never essential
        log.debug("tray notification failed", exc_info=True)


def running() -> bool:
    return _icon is not None
