"""Action events: an in-memory SSE bus + persistence through db.

The chat stream carries actions while a request runs. Anything that updates an
action *after* the stream ends (install confirmations) goes through this bus.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any, AsyncIterator

from . import db

_MAX = 200
_LOCK = threading.Lock()
_SUBS: list[queue.Queue] = []
HEARTBEAT = 15.0


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=_MAX)
    with _LOCK:
        _SUBS.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _LOCK:
        if q in _SUBS:
            _SUBS.remove(q)


def publish(action: dict[str, Any]) -> dict[str, Any]:
    """Persist (if the message row exists) and fan out to every listener."""
    try:
        saved = db.update_action(action.get("id"), action)
        if saved is not None:
            action = saved
    except Exception:  # noqa: BLE001 - never break a run over bookkeeping
        pass
    with _LOCK:
        subs = list(_SUBS)
    for q in subs:
        try:
            q.put_nowait(dict(action))
        except queue.Full:
            pass  # slow listener: drop rather than block the tool
    return action


async def events() -> AsyncIterator[str]:
    """SSE body for GET /api/actions."""
    q = subscribe()
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                action = await loop.run_in_executor(None, lambda: q.get(True, HEARTBEAT))
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(action, ensure_ascii=False)}\n\n"
    finally:
        unsubscribe(q)


def subscriber_count() -> int:
    with _LOCK:
        return len(_SUBS)
