"""Mot launcher — double-click to start (no terminal window).

Explorer may open .pyw files in IDLE, so the supported way to start Mot is the
Desktop shortcut (python tools\\make_shortcut.py), which calls pythonw.exe on this
file directly. However Mot is started, a startup failure here always writes
logs/crash.log AND shows a plain-English message box — never silence.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CRASH_LOG = ROOT / "logs" / "crash.log"
FRONTEND_INDEX = ROOT / "frontend" / "dist" / "index.html"


def write_crash(text: str) -> None:
    """Append to logs/crash.log — the only record pythonw leaves behind."""
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
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


if __name__ == "__main__":
    try:
        check_frontend()
        from backend.main import main

        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - report everything, never die silently
        detail = "".join(traceback.format_exception(exc)).rstrip()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_crash(f"\n=== {stamp} ===\n{detail}\n")
        message_box(friendly(exc))
        sys.exit(1)
