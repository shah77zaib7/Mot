"""Saved routines — data/routines.json. Steps are plain tool calls, no LLM."""
from __future__ import annotations

import json
import re
import threading
from typing import Any

from .config import DATA_DIR

ROUTINES_PATH = DATA_DIR / "routines.json"
STEP_ACTIONS = ("open_url", "open_app")  # what the routines editor offers
_LOCK = threading.Lock()

DEFAULT_ROUTINE: dict[str, Any] = {
    "id": "morning-setup",
    "name": "Morning setup",
    "steps": [
        {"action": "open_url",
         "url": "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD&interval=1"},
        {"action": "open_app", "name": "chrome"},
        {"action": "open_app", "name": "whatsapp"},
    ],
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "routine"


def load() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if not ROUTINES_PATH.exists():
            data = {"routines": [json.loads(json.dumps(DEFAULT_ROUTINE))]}
            ROUTINES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        try:
            data = json.loads(ROUTINES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"routines": [json.loads(json.dumps(DEFAULT_ROUTINE))]}
    if not isinstance(data, dict) or not isinstance(data.get("routines"), list):
        return {"routines": [json.loads(json.dumps(DEFAULT_ROUTINE))]}
    return data


def save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        ROUTINES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_routines() -> list[dict[str, Any]]:
    return load().get("routines", [])


def get(name_or_id: str) -> dict[str, Any] | None:
    needle = (name_or_id or "").strip().lower()
    if not needle:
        return None
    for routine in list_routines():
        if routine.get("id") == needle or str(routine.get("name", "")).lower() == needle:
            return routine
    return None


def clean_step(step: Any) -> dict[str, Any] | None:
    if not isinstance(step, dict):
        return None
    action = str(step.get("action") or "")
    if action == "open_url":
        url = str(step.get("url") or "").strip()
        return {"action": "open_url", "url": url} if url else None
    if action == "open_app":
        name = str(step.get("name") or "").strip()
        return {"action": "open_app", "name": name} if name else None
    return None


def upsert(routine: dict[str, Any]) -> dict[str, Any]:
    """Create or update one routine. Raises ValueError on bad input."""
    name = str(routine.get("name") or "").strip()
    if not name:
        raise ValueError("Routine name is required.")
    steps = [clean_step(s) for s in routine.get("steps") or []]
    steps = [s for s in steps if s]
    if not steps:
        raise ValueError("A routine needs at least one step.")

    data = load()
    rid = str(routine.get("id") or "").strip() or _slug(name)
    item = {"id": rid, "name": name, "steps": steps}
    routines = data.setdefault("routines", [])
    at = next((i for i, r in enumerate(routines) if r.get("id") == rid), None)
    if at is None:
        if any(str(r.get("name", "")).lower() == name.lower() for r in routines):
            raise ValueError(f"A routine called \u201c{name}\u201d already exists.")
        routines.append(item)
    else:
        routines[at] = item
    save(data)
    return item


def delete(routine_id: str) -> bool:
    data = load()
    before = len(data.get("routines", []))
    data["routines"] = [r for r in data.get("routines", []) if r.get("id") != routine_id]
    if len(data["routines"]) == before:
        return False
    save(data)
    return True
