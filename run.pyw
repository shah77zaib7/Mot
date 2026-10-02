"""Mot launcher — double-click to start (no terminal window).

Explorer may open .pyw files in IDLE, so the supported way to start Mot is the
Desktop shortcut (python tools\\make_shortcut.py), which calls pythonw.exe on this
file directly. However Mot is started, a startup failure here always writes
crash.log AND shows a plain-English message box — never silence.

Paths: program files live next to this file, the user's data and logs live in
`backend/core/paths.py` (%APPDATA%\\Mot). Nothing here hardcodes a folder.
"""
from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BOOT = time.perf_counter()  # for the "window on screen after N s" log line

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core import paths  # noqa: E402 - stdlib only, safe this early

# Program files stay next to run.pyw; the log lives with the user's data.
FRONTEND_INDEX = paths.frontend_dist() / "index.html"
CRASH_LOG = paths.log_dir() / "crash.log"
LOG_PATH = paths.log_dir() / "mot.log"


def note(text: str) -> None:
    """One line in mot.log — pythonw has no console to say it on."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} INFO mot: {text}\n")
    except OSError:
        pass


def write_crash(text: str) -> None:
    """Append to crash.log — the only record pythonw leaves behind."""
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        pass


def close_splash() -> None:
    """Take the starting window down — a no-op when there is none."""
    try:
        from backend.core import splash

        splash.close()
    except Exception:  # noqa: BLE001 - never let cleanup hide the real error
        pass


def message_box(text: str) -> None:
    """pythonw has no console: say it where the user can see it."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Mot could not start", 0x10)  # MB_ICONERROR
    except Exception:  # noqa: BLE001 - a message box must never mask the real error
        pass


def friendly(exc: BaseException) -> str:
    """Plain English for the box; the traceback still lands in logs/crash.log."""
    if isinstance(exc, ModuleNotFoundError):
        name = (exc.name or "").split(".")[0]
        if name in {"backend", "tools", "frontend"}:  # ours, not pip's
            return (
                f'Mot\'s own module "{exc.name}" is missing, so this folder looks '
                f"incomplete.\n\nMake sure everything under {ROOT} is still there, "
                "then start Mot again."
            )
        return (
            f'Mot is missing the Python package "{exc.name}".\n\n'
            "Open a terminal in this folder and run:\n"
            "    pip install -r requirements.txt"
        )
    text = str(exc).strip()
    if text:
        return text
    return (
        f"Mot could not start ({type(exc).__name__}).\n\n"
        f"Details are in {CRASH_LOG}."
    )


def check_frontend() -> None:
    """A missing build is the most common first-run failure — say so up front."""
    if FRONTEND_INDEX.is_file():
        return
    raise RuntimeError(
        "The Mot interface has not been built yet.\n\n"
        "Open a terminal in this folder and run:\n"
        "    cd frontend\n"
        "    npm install\n"
        "    npm run build\n\n"
        "Then start Mot again."
    )


def one_instance() -> None:
    """One Mot at a time, checked before anything heavy is imported.

    A second launch pokes the running instance (so it comes to the front) and
    leaves silently; `wake=False` under `--background` means auto-start never
    pops a window over the one you are already using. `--serve` is the
    developer's exception — backend.main does its own check there.

    This runs inside the try below on purpose: if the check itself breaks, that
    is a real failure and must reach crash.log and the message box, not vanish.
    """
    from backend.core import singleinstance

    if "--serve" in sys.argv or singleinstance.acquire(
        wake="--background" not in sys.argv
    ):
        return
    note("second launch: Mot is already running, asked it to come to the front")
    raise SystemExit(0)


if __name__ == "__main__":
    try:
        one_instance()
        check_frontend()
        from backend.main import main

        main(started=BOOT)
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - report everything, never die silently
        close_splash()  # take it down before the error box appears
        detail = "".join(traceback.format_exception(exc)).rstrip()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_crash(f"\n=== {stamp} ===\n{detail}\n")
        message_box(friendly(exc))
        sys.exit(1)
    finally:
        close_splash()
