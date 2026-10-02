"""Plain-English failures: log the traceback, show one short sentence.

Two rules for the whole app, and this module is where they live:

* an error is **never a blank screen** — the UI always gets a sentence;
* the detail always goes to `logs/mot.log`, never in front of the user.

`friendly()` is what the UI sees; `log_exception()` is what the log gets.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("mot")

GENERIC = "Mot hit a problem while doing that. The details are in the log."
OFFLINE = ("Mot can't reach the internet for that right now. "
           "Check your connection and try again.")
NO_SERVER = ("Mot's own server is not answering. "
             "Use Quit Mot in the tray, then start Mot again.")

# Messages that are code talking to itself ("'providers'", "unsupported operand
# type(s)") — never useful in front of a person.
_RAW = (KeyError, AttributeError, TypeError, NameError, IndexError,
        RecursionError, ZeroDivisionError, UnboundLocalError)

MAX_LEN = 220


def friendly(exc: BaseException, *, generic: str = GENERIC) -> str:
    """One short sentence for the UI. The traceback still goes to the log."""
    if isinstance(exc, _RAW):
        return generic
    text = str(getattr(exc, "message", "") or exc)
    text = " ".join(text.split())
    if not text:
        return generic
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN].rstrip() + "…"
    return text


def log_exception(where: str, exc: BaseException) -> None:
    """Full traceback into logs/mot.log, tagged with where it happened."""
    log.error("%s: %s", where, friendly(exc), exc_info=exc)


def describe(request_url: str, exc: BaseException) -> dict[str, Any]:
    """The JSON body an API error answers with."""
    return {"detail": friendly(exc), "path": request_url}
