"""Settings > Apps: aliases, preferred browser, re-scan."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import apps

router = APIRouter(prefix="/api", tags=["apps"])


class AppsIn(BaseModel):
    aliases: dict[str, str] | None = None
    browser: str | None = None


def _payload() -> dict[str, Any]:
    data = apps.load()
    return {
        "names": [a["name"] for a in data.get("apps", [])],
        "count": len(data.get("apps", [])),
        "aliases": data.get("aliases", {}),
        "browser": data.get("browser", "default"),
        "scanned_at": data.get("scanned_at", 0.0),
    }


@router.get("/apps")
def get_apps() -> dict[str, Any]:
    return _payload()


@router.post("/apps/rescan")
async def rescan() -> dict[str, Any]:
    try:
        await asyncio.to_thread(apps.scan)
    except Exception as exc:  # noqa: BLE001 - PowerShell problems are friendly here
        raise HTTPException(
            400, "Couldn't scan the Start Menu: " + " ".join(str(exc).split())[:200]
        ) from exc
    return _payload()


@router.put("/apps")
def update_apps(body: AppsIn) -> dict[str, Any]:
    if body.aliases is not None:
        apps.set_aliases(body.aliases)
    if body.browser is not None:
        if body.browser not in apps.BROWSERS:
            raise HTTPException(400, "Unknown browser preference.")
        apps.set_browser(body.browser)
    return _payload()
