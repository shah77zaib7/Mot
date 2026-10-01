"""Background feed refresh — a plain thread, no scheduler library.

Runs once when the desktop app starts, then every `interval_hours` (default 2),
and writes data/market_ingest/latest.json for get_news to read first. Settings >
Feeds turns it off, changes the interval, or runs it now; `last_ingest_at` comes
from the snapshot itself so it survives a restart.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from . import feeds, snapshot

log = logging.getLogger("mot")

DEFAULTS: dict[str, Any] = {"enabled": True, "interval_hours": 2.0}
MIN_HOURS = 0.25  # 15 min, for people who want it hotter
MAX_HOURS = 24.0
TICK = 30.0  # how often the loop re-reads the settings

_LOCK = threading.Lock()
_BUSY = threading.Lock()  # one refresh at a time, background or button
_STOP = threading.Event()
_thread: threading.Thread | None = None


def _path() -> Any:
    """Settings live beside the snapshot, so tests can move both at once."""
    return snapshot.PATH.parent / "settings.json"


def _hours(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(DEFAULTS["interval_hours"])
    return min(MAX_HOURS, max(MIN_HOURS, number))


def settings() -> dict[str, Any]:
    """The loop's settings plus the last time a refresh finished."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out["enabled"] = bool(raw.get("enabled", out["enabled"]))
        out["interval_hours"] = _hours(raw.get("interval_hours"))
    out["last_ingest_at"] = snapshot.fetched_at()
    return out


def save(patch: dict[str, Any]) -> dict[str, Any]:
    """Store Settings > Feeds (interval / on-off) and report the result."""
    current = settings()
    if "enabled" in patch:
        current["enabled"] = bool(patch["enabled"])
    if "interval_hours" in patch:
        current["interval_hours"] = _hours(patch["interval_hours"])
    payload = {
        "enabled": current["enabled"],
        "interval_hours": current["interval_hours"],
    }
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:  # unwritable folder: still honoured for this session
        log.warning("can't write the feed refresh settings")
    return status()


def status() -> dict[str, Any]:
    """Everything Settings > Feeds and the news card show."""
    return {**settings(), **snapshot.summary()}


def refresh_now() -> dict[str, Any]:
    """One run right now (the "Refresh now" button and the startup pass).

    Returns {"ok": False, "busy": True} when a run is already going.
    """
    if not _BUSY.acquire(blocking=False):
        return {"ok": False, "busy": True}
    try:
        return {"ok": True, **feeds.refresh_all()}
    finally:
        _BUSY.release()


def _loop() -> None:
    next_run = time.time()  # once at startup…
    while not _STOP.is_set():
        now = time.time()
        if now >= next_run:
            if settings()["enabled"]:
                try:
                    refresh_now()
                except Exception:  # pragma: no cover - a dead network is fine
                    log.warning("feed refresh failed", exc_info=True)
            next_run = time.time() + settings()["interval_hours"] * 3600
        if _STOP.wait(TICK):  # …then every interval_hours, honouring new settings
            break


def start() -> None:
    """Start the background loop. Idempotent; called by the desktop entry."""
    global _thread
    with _LOCK:
        if _thread is not None and _thread.is_alive():
            return
        _STOP.clear()
        _thread = threading.Thread(target=_loop, name="mot-ingest", daemon=True)
        _thread.start()
    log.info("feed refresh on: every %s h", settings()["interval_hours"])


def stop() -> None:
    """Ask the loop to exit and wait for it (tests, clean shutdown)."""
    _STOP.set()
    thread = _thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=2.0)
