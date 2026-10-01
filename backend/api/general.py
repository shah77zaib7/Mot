"""Settings > General — close behaviour, the global shortcut, auto-start."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import autostart, config, hotkey

router = APIRouter(prefix="/api", tags=["general"])
log = logging.getLogger("mot")


class GeneralIn(BaseModel):
    close_to_tray: bool | None = None
    hotkey: str | None = None
    autostart: bool | None = None


def state() -> dict[str, Any]:
    general = config.general()
    combo = general["hotkey"]
    try:
        pretty = hotkey.label(combo)
    except ValueError:
        pretty = combo
    info = hotkey.status()
    return {
        "close_to_tray": general["close_to_tray"],
        "hotkey": combo,
        "hotkey_label": pretty,
        "hotkey_active": info["active"],
        "hotkey_error": info["error"],
        "autostart": autostart.enabled(),
    }


@router.get("/general")
def get_general() -> dict:
    return state()


@router.put("/general")
def put_general(body: GeneralIn) -> dict:
    """One field at a time; a refused shortcut keeps the old one."""
    if body.close_to_tray is not None:
        config.set_general({"close_to_tray": body.close_to_tray})
        log.info("when Mot closes: %s",
                 "go to the tray" if body.close_to_tray else "quit")

    if body.hotkey is not None:
        ok, message = hotkey.apply(body.hotkey)
        if not ok:
            return {"ok": False, "message": message, **state()}
        config.set_general({"hotkey": body.hotkey})
        log.info("hotkey: %s", body.hotkey)

    if body.autostart is not None:
        try:
            autostart.set_enabled(body.autostart)
        except (OSError, RuntimeError) as exc:
            return {"ok": False, "message": str(exc), **state()}
        log.info("auto-start: %s", "on" if body.autostart else "off")

    return {"ok": True, "message": None, **state()}
