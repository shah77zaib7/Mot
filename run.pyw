"""Mot launcher — double-click to start (no terminal window)."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    try:
        from backend.main import main

        main()
    except BaseException:
        # With pythonw there is no console: keep the traceback where we can read it.
        crash = ROOT / "logs" / "crash.log"
        try:
            crash.parent.mkdir(exist_ok=True)
            with crash.open("a", encoding="utf-8") as handle:
                handle.write(traceback.format_exc())
        except OSError:
            pass
        raise
