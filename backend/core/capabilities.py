"""What Mot can and cannot do — one line, built from the tool registry.

The system prompt never hard-codes Mot's abilities: add a tool in `tools/`
and the line changes on the next message. Anything Mot has no tool for is
listed as a "cannot", so a model is told the truth about its own reach.
"""
from __future__ import annotations

from ..tools import registry

# Short label per known tool; an unlisted tool falls back to its own name.
CAN_WORDS: dict[str, str] = {
    "open_url": "open sites",
    "open_app": "open apps",
    "search_in_browser": "site search",
    "install_app": "install apps",
    "play_youtube": "play YouTube",
    "whatsapp_message": "WhatsApp",
    "get_news": "news",
    "web_search": "web search",
    "run_routine": "routines",
}

# (name fragments, phrase) — shown only while NO registered tool matches them.
CANNOT_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("shell", "terminal", "powershell", "exec", "run_command", "bash"),
     "run shell commands"),
    (("screen", "screenshot", "mouse", "keyboard", "click"),
     "control the screen"),
    (("trade", "place_order", "buy", "sell"),
     "place trades"),
)


def can_words() -> list[str]:
    return [CAN_WORDS.get(name, name.replace("_", " ")) for name in sorted(registry.TOOLS)]


def cannot_words() -> list[str]:
    names = list(registry.TOOLS)
    out = [
        phrase
        for keys, phrase in CANNOT_RULES
        if not any(key in name for name in names for key in keys)
    ]
    # Always true: only the Confirm button in the UI moves an action forward.
    out.append("confirm its own actions")
    return out


def _join(words: list[str]) -> str:
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + ", or " + words[-1]


def line() -> str:
    """`Can: open apps, ... . Cannot: ... , or confirm its own actions.`"""
    return f"Can: {_join(can_words())}. Cannot: {_join(cannot_words())}."
