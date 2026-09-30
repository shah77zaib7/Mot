"""open_app — fuzzy-match a name against installed apps and start it."""
from __future__ import annotations

from typing import Any

from ..core import apps
from . import launch
from .registry import register

NOT_FOUND_HINT = (
    'Say \u201cinstall {name}\u201d to install it, or add an alias in Settings \u2192 Apps.'
)


@register(
    "open_app",
    "Open an installed Windows desktop app by name (fuzzy match + aliases, e.g. "
    "chrome, whatsapp, notepad). Try this first for anything that is an installed app.",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "App name"}},
        "required": ["name"],
    },
)
def open_app(args: dict[str, Any]) -> dict[str, Any]:
    name = (args.get("name") or "").strip()
    if not name:
        return {"ok": False, "message": "No app name given.", "data": {}}

    entry = apps.match(name)
    if entry is None:
        return {
            "ok": False,
            "message": f'Couldn\u2019t find an app called \u201c{name}\u201d.',
            "data": {"name": name, "hint": NOT_FOUND_HINT.format(name=name)},
        }

    result = launch.launch_app(entry)
    if not result.get("ok"):
        return {
            "ok": False,
            "message": f"Couldn\u2019t open {entry['name']}. {result.get('message', '')}".strip(),
            "data": {"name": name},
        }
    return {
        "ok": True,
        "message": f"Opened {entry['name']}.",
        "data": {"app": entry["name"], "label": entry["name"]},
    }
