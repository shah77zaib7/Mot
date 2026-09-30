"""run_routine — run a saved routine's steps (no model involved)."""
from __future__ import annotations

from typing import Any

from ..core import routines
from .registry import register


@register(
    "run_routine",
    "Run a saved routine by name (a list of open-url / open-app steps).",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Routine name"}},
        "required": ["name"],
    },
)
def run_routine(args: dict[str, Any]) -> dict[str, Any]:
    name = (args.get("name") or "").strip()
    routine = routines.get(name)
    if routine is None:
        known = ", ".join(r["name"] for r in routines.list_routines()) or "none yet"
        return {
            "ok": False,
            "message": f"No routine called \u201c{name}\u201d. Saved routines: {known}.",
            "data": {},
        }
    # Imported here: core.runner imports the tool registry (no import cycle).
    from ..core import runner

    actions = runner.run_steps(routine.get("steps", []))
    done = sum(1 for a in actions if a["status"] == "done")
    failed = [a for a in actions if a["status"] == "failed"]
    message = f'Ran \u201c{routine["name"]}\u201d — {done}/{len(actions)} steps done.'
    if failed:
        message += " " + failed[0].get("message", "")
    return {"ok": not failed, "message": message, "data": {"steps": actions}}
