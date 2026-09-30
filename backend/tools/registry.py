"""Tool registry: one entry per tool, every tool returns {ok, message, data}.

Adding a tool = one file in tools/ + a @register decorator (see Architecture.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

Args = dict[str, Any]
Result = dict[str, Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    func: Callable[[Args], Result]


TOOLS: dict[str, Tool] = {}


def register(name: str, description: str, schema: dict[str, Any]):
    """Decorate a function so it becomes a callable tool."""

    def deco(func: Callable[[Args], Result]) -> Callable[[Args], Result]:
        TOOLS[name] = Tool(name, description, schema, func)
        return func

    return deco


def get(name: str) -> Tool | None:
    return TOOLS.get(name)


def spec() -> list[dict[str, Any]]:
    """Tool list for the LLM path (Phase 3)."""
    return [
        {"name": t.name, "description": t.description, "schema": t.schema}
        for t in TOOLS.values()
    ]


def call(name: str, args: Args | None = None) -> Result:
    """Run one tool. Never raises: failures come back as {ok: False, message}."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "message": f"Mot can't run '{name}'.", "data": {}}
    try:
        result = tool.func(args or {}) or {}
    except Exception as exc:  # noqa: BLE001 - a broken tool must not kill a chat
        short = " ".join(str(exc).split())[:200]
        return {"ok": False, "message": short or f"'{name}' failed.", "data": {}}
    result.setdefault("ok", True)
    result.setdefault("message", "")
    result.setdefault("data", {})
    return result
