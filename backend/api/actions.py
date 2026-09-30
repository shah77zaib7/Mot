"""Action events + confirmation (install cards after the chat stream ends)."""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import actions, db
from ..tools import install as install_tool
from ..tools import whatsapp as whatsapp_tool

router = APIRouter(prefix="/api", tags=["actions"])

HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

THROTTLE = 0.4  # seconds between winget progress lines


class ConfirmIn(BaseModel):
    confirm: bool = True


def _install(action_id: str, package: dict[str, Any]) -> None:
    """winget install on a worker thread, streaming progress to the UI."""
    state = {"last": 0.0}

    def on_line(line: str) -> None:
        now = time.time()
        if now - state["last"] < THROTTLE:
            return
        state["last"] = now
        actions.publish({"id": action_id, "detail": line.strip()[:160]})

    result = install_tool.install(package, on_line=on_line)
    label = package.get("name") or package.get("id") or "the app"
    if result["ok"]:
        actions.publish({
            "id": action_id,
            "status": "done",
            "title": f"Installed {label}",
            "detail": package.get("id"),
            "message": result["message"],
        })
    else:
        actions.publish({
            "id": action_id,
            "status": "failed",
            "title": result["message"],
            "detail": "Open a terminal and run winget yourself, or try again.",
            "message": result["message"],
        })


def _whatsapp(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Open the chat — the user already pressed Confirm."""
    contact = payload.get("contact") or {}
    name = contact.get("name") or "them"
    result = whatsapp_tool.open_chat(payload)
    patch: dict[str, Any] = {
        "id": action_id,
        "status": "done" if result.get("ok") else "failed",
        "title": result.get("message") or f"Couldn\u2019t open WhatsApp for {name}.",
        "message": result.get("message") or "",
    }
    data = result.get("data") or {}
    if data.get("note"):
        patch["detail"] = data["note"]
    elif data.get("hint"):
        patch["detail"] = data["hint"]
    return actions.publish(patch)


@router.get("/actions")
async def action_events():  # noqa: ANN201 - StreamingResponse typed below
    from fastapi.responses import StreamingResponse

    return StreamingResponse(actions.events(), media_type="text/event-stream", headers=HEADERS)


@router.post("/actions/{action_id}")
def confirm_action(action_id: str, body: ConfirmIn) -> dict[str, Any]:
    stored = db.find_action(action_id)
    if stored is None:
        raise HTTPException(404, "That action is no longer available.")
    if stored.get("status") != "needs_confirm":
        raise HTTPException(400, "There is nothing to confirm here.")
    payload = stored.get("data") or {}
    is_whatsapp = bool(payload.get("contact"))

    if not body.confirm:
        what = "nothing was sent" if is_whatsapp else "nothing was installed"
        updated = actions.publish({
            "id": action_id,
            "status": "cancelled",
            "detail": f"Cancelled \u2014 {what}.",
            "message": f"Cancelled \u2014 {what}.",
        })
        return {"ok": True, "action": updated}

    if is_whatsapp:
        actions.publish({"id": action_id, "status": "running",
                         "detail": "Opening WhatsApp\u2026"})
        return {"ok": True, "action": _whatsapp(action_id, payload)}

    package = (stored.get("data") or {}).get("package") or {}
    if not install_tool.winget_available():
        raise HTTPException(400, "winget isn't available on this Windows install.")
    actions.publish({"id": action_id, "status": "running", "detail": "Starting winget\u2026"})
    threading.Thread(target=_install, args=(action_id, package), daemon=True).start()
    return {"ok": True, "action": stored}
