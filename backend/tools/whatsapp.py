"""whatsapp_message — pre-fill a chat to a saved contact (always Confirm first).

The tool never sends: it stops at a Confirm card holding the contact and the
text, and only after the user presses Confirm does `open_chat()` run, opening
whatsapp://send?phone=&text= (falling back to https://wa.me/... when Windows
has no handler for the desktop link).
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from ..core import apps, contacts
from . import launch
from .registry import register

ADD_HINT = "Add them in Settings \u2192 Contacts first."
SCHEME = "whatsapp://send?phone={phone}&text={text}"
WA_ME = "https://wa.me/{phone}?text={text}"


def digits(phone: Any) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def build_urls(phone: str, text: str) -> tuple[str, str]:
    """(desktop link, browser link) for one message."""
    number, body = digits(phone), quote(str(text or ""), safe="")
    return SCHEME.format(phone=number, text=body), WA_ME.format(phone=number, text=body)


@register(
    "whatsapp_message",
    "Open a WhatsApp chat to a contact saved in Settings > Contacts with the "
    "message pre-filled. Always shows a Confirm card first and never sends by "
    "itself. Unknown contacts must be reported, never guessed.",
    {
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "Contact name as the user said it"},
            "text": {"type": "string", "description": "Message to pre-fill"},
        },
        "required": ["contact", "text"],
    },
)
def whatsapp_message(args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("contact") or "").strip()
    text = str(args.get("text") or "").strip()
    if not name:
        return {"ok": False, "message": "No contact given.", "data": {}}
    if not text:
        return {"ok": False, "message": "There is no message to send.", "data": {}}

    person = contacts.match(name)
    if person is None:
        return {
            "ok": False,
            "message": f"I don\u2019t have a contact called \u201c{name}\u201d.",
            "data": {"contact_name": name, "hint": ADD_HINT},
        }
    if not digits(person.get("phone")):
        return {
            "ok": False,
            "message": f"{person['name']} has no phone number saved.",
            "data": {"contact_name": person["name"], "hint": ADD_HINT},
        }

    primary, fallback = build_urls(str(person["phone"]), text)
    return {
        "ok": True,
        "message": f"Send \u201c{text}\u201d to {person['name']}?",
        "data": {
            "needs_confirm": True,
            "contact": {"name": person["name"], "phone": person["phone"]},
            "text": text,
            "url": primary,
            "fallback_url": fallback,
        },
    }


def open_chat(data: dict[str, Any]) -> dict[str, Any]:
    """Open the chat — only ever called after the user pressed Confirm."""
    contact = data.get("contact") or {}
    name = str(contact.get("name") or "them")
    text = str(data.get("text") or "")

    result = launch.open_scheme(str(data.get("url") or ""))
    if result.get("ok"):
        return {"ok": True, "message": f"Opened WhatsApp for {name}."}

    fallback = str(data.get("fallback_url") or "")
    if fallback:
        result = launch.open_url(fallback, browser=apps.browser())
        if result.get("ok"):
            return {
                "ok": True,
                "message": f"Opened WhatsApp for {name}.",
                "data": {"note": "Desktop link unavailable \u2014 used wa.me instead."},
            }
    return {
        "ok": False,
        "message": f"Couldn\u2019t open WhatsApp for {name}.",
        "data": {"text": text, "hint": "Open WhatsApp once by hand, then try again."},
    }
