"""Drex — POST /api/drex/check (Settings > Drex)."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..core import drex

router = APIRouter(prefix="/api", tags=["drex"])
log = logging.getLogger("mot")


@router.post("/drex/check")
async def drex_check() -> dict:
    """One live round trip; friendly errors with the dashboard link."""
    try:
        result = drex.check()
    except drex.DrexError as exc:
        log.warning("drex check failed: %s", exc.code)
        return {"ok": False, "message": exc.message, "code": exc.code, "has_key": drex.has_key()}
    return result
