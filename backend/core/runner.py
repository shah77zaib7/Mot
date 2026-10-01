"""Run fast-path steps and turn them into action cards — no model involved.

Every step becomes an action: {id, chat_id, kind, title, detail, status, data}.
Statuses: running -> done | failed | needs_confirm -> (Confirm) -> done | cancelled.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from . import routines
from ..tools import registry
from ..tools.open_url import label_for
from ..tools.search import DISPLAY, engine_key

Emit = Callable[[dict[str, Any]], None]

IDLE_TITLES: dict[str, str] = {
    "open_url": "Opening {name}",
    "search_in_browser": "Searching for \u201c{name}\u201d",
    "open_app": "Opening {name}",
    "install_app": "Looking for {name} on winget",
    "run_routine": "Running \u201c{name}\u201d",
    "play_youtube": "Finding \u201c{name}\u201d on YouTube",
    "whatsapp_message": "Preparing a WhatsApp to {name}",
    "get_news": "Checking {name} news",
    "web_search": "Searching the web for \u201c{name}\u201d",
}


def _new_action(kind: str, step: dict[str, Any], chat_id: str | None) -> dict[str, Any]:
    name = (
        step.get("query")
        or step.get("topic")
        or step.get("name")
        or step.get("contact")
        or step.get("url")
        or ""
    )
    if kind == "open_url":
        name = label_for(str(step.get("url") or ""))
    title = IDLE_TITLES.get(kind, str(name)).format(name=name)
    return {
        "id": uuid.uuid4().hex[:16],
        "chat_id": chat_id,
        "kind": kind,
        "title": title,
        "detail": None,
        "status": "running",
        "data": {},
        "message": "",
        "phrase": "",
        "steps": None,
    }


def _emit(emit: Emit | None, action: dict[str, Any]) -> None:
    if emit is None:
        return
    try:
        emit(dict(action))
    except Exception:  # noqa: BLE001 - a closed stream must not kill the run
        pass


def _phrase(kind: str, step: dict[str, Any], data: dict[str, Any]) -> str:
    if kind == "open_url":
        return f"opened {data.get('label') or step.get('url')}"
    if kind == "search_in_browser":
        label = data.get("label") or DISPLAY.get(engine_key(str(step.get("site") or "")), "the web")
        return f"searched {label} for \u201c{step.get('query')}\u201d"
    if kind == "open_app":
        return f"opened {data.get('label') or step.get('name')}"
    if kind == "run_routine":
        return f"ran \u201c{step.get('name')}\u201d"
    if kind == "play_youtube":
        if data.get("fallback"):
            return f"searched YouTube for \u201c{step.get('query')}\u201d"
        return f"played \u201c{step.get('query')}\u201d on YouTube"
    if kind == "whatsapp_message":
        name = (data.get("contact") or {}).get("name") or step.get("contact")
        return f"opened a WhatsApp chat for {name}"
    if kind == "get_news":
        count = len(data.get("items") or [])
        return f"showed {count} {step.get('topic') or 'news'} headlines"
    if kind == "web_search":
        return f"searched the web for \u201c{step.get('query')}\u201d"
    return ""


def _apply_result(
    action: dict[str, Any], kind: str, step: dict[str, Any], result: dict[str, Any]
) -> None:
    data = result.get("data") or {}
    message = (result.get("message") or "").strip()

    if data.get("needs_confirm"):
        contact = data.get("contact")
        if contact:  # whatsapp_message: the person and the message, then Confirm
            action.update(
                status="needs_confirm",
                title=f"Send \u201c{data.get('text') or ''}\u201d to {contact.get('name')}?",
                detail=f"{contact.get('phone')} \u00b7 WhatsApp",
                data={k: v for k, v in data.items() if k != "steps"},
                message=message,
            )
            return
        package = data.get("package") or {}
        action.update(
            status="needs_confirm",
            title=f"Install {package.get('name') or step.get('name')}?",
            detail=f"{package.get('id')} \u00b7 winget",
            data={"package": package},
            message=message,
        )
        return

    if result.get("ok"):
        action.update(
            status="done",
            title=(message.rstrip(".") or "Done"),
            # A news card already carries "Updated HH:MM" in its footer line, so it
            # must not say the time twice under the title.
            detail=(None if data.get("updated") and data.get("note")
                    else data.get("note") or data.get("url")),
            data={k: v for k, v in data.items() if k != "steps"},
            message=message,
            phrase=_phrase(kind, step, data),
        )
    else:
        action.update(
            status="failed",
            title=message or "That didn\u2019t work.",
            detail=(data.get("hint") or data.get("url") or None),
            data=data,
            message=message,
        )


def _run_routine(action: dict[str, Any], step: dict[str, Any], emit: Emit | None) -> None:
    name = str(step.get("name") or "").strip()
    routine = routines.get(name)
    if routine is None:
        action.update(
            status="failed",
            title=f"No routine called \u201c{name}\u201d.",
            detail="Create it in Settings \u2192 Routines.",
            message=f"No routine called \u201c{name}\u201d.",
        )
        return

    children = run_steps(routine.get("steps", []), emit=None, chat_id=action["chat_id"])
    action["steps"] = [
        {"title": c["title"], "status": c["status"], "detail": c.get("detail")}
        for c in children
    ]
    done = sum(1 for c in children if c["status"] == "done")
    failed = [c for c in children if c["status"] == "failed"]
    action.update(
        status="failed" if failed and done == 0 else "done",
        title=f"Ran \u201c{routine['name']}\u201d",
        detail=f"{done}/{len(children)} steps done" + (f" \u00b7 {failed[0]['title']}" if failed else ""),
        data={"routine": routine["id"]},
        message=f"Ran \u201c{routine['name']}\u201d \u2014 {done}/{len(children)} steps done.",
        phrase=_phrase("run_routine", {"name": routine["name"]}, {}),
    )


def _execute(step: dict[str, Any], emit: Emit | None, chat_id: str | None) -> dict[str, Any]:
    kind = str(step.get("action") or "")
    action = _new_action(kind, step, chat_id)
    _emit(emit, action)
    if kind == "install_app":
        result = registry.call(kind, step)
        _apply_result(action, kind, step, result)
    elif kind == "run_routine":
        _run_routine(action, step, emit)
    else:
        result = registry.call(kind, step)
        _apply_result(action, kind, step, result)
    _emit(emit, action)
    return action


def run_steps(
    steps: list[dict[str, Any]],
    emit: Emit | None = None,
    chat_id: str | None = None,
) -> list[dict[str, Any]]:
    return [_execute(dict(step), emit, chat_id) for step in steps or []]


def summary(actions: list[dict[str, Any]]) -> str:
    """One short reply line for what just happened."""
    if not actions:
        return "Done."
    good = [a["phrase"] for a in actions if a["status"] == "done" and a.get("phrase")]
    pending = [a for a in actions if a["status"] == "needs_confirm"]
    bad = [a for a in actions if a["status"] in ("failed", "cancelled")]

    parts: list[str] = []
    if good:
        if len(good) == 1:
            sentence = good[0]
        elif len(good) == 2:
            sentence = " and ".join(good)
        else:
            sentence = ", ".join(good[:-1]) + ", and " + good[-1]
        parts.append(sentence[0].upper() + sentence[1:] + ".")
    for action in pending:
        parts.append(f"{action['title']} Press Confirm to continue.")
    for action in bad:
        text = (action.get("message") or action.get("title") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)
