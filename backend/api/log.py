"""POST /api/log — where the frontend's errors land.

A browser inside pywebview has no console the user will ever read, so the UI
sends its render errors and unhandled rejections here and they end up in
`logs/mot.log` next to the backend's own tracebacks. Messages are truncated
and one-line-ified: this is a breadcrumb trail, not a data channel.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("mot")

MAX = 2000
router = APIRouter(prefix="/api", tags=["log"])


class BrowserError(BaseModel):
    message: str = ""
    stack: str = ""
    source: str = "js"


@router.post("/log")
def browser_error(body: BrowserError) -> dict:
    message = " ".join(str(body.message).split())[:MAX] or "(no message)"
    stack = " ".join(str(body.stack).split())[:MAX]
    source = " ".join(str(body.source).split())[:60]
    log.error("frontend error (%s): %s", source, message)
    if stack:
        log.error("frontend stack: %s", stack)
    return {"ok": True}
