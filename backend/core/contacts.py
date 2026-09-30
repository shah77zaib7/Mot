"""Saved contacts — data/contacts.json (Settings > Contacts).

Only what the user saved here is ever messaged: `match()` is deliberately
conservative so Mot never guesses a wrong person.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any

from .config import DATA_DIR

CONTACTS_PATH = DATA_DIR / "contacts.json"
_LOCK = threading.Lock()


def _norm(text: Any) -> str:
    """Lowercase, drop everything that isn't a letter or a digit."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _digits(phone: Any) -> str:
    return re.sub(r"\D", "", str(phone or ""))


def load() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if not CONTACTS_PATH.exists():
            data: dict[str, Any] = {"contacts": []}
            CONTACTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        try:
            data = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"contacts": []}
    if not isinstance(data, dict) or not isinstance(data.get("contacts"), list):
        return {"contacts": []}
    return data


def save(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        CONTACTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_contacts() -> list[dict[str, Any]]:
    return load().get("contacts", [])


def get(contact_id: str) -> dict[str, Any] | None:
    needle = (contact_id or "").strip().lower()
    if not needle:
        return None
    return next(
        (c for c in list_contacts() if str(c.get("id", "")).lower() == needle), None
    )


def match(name: str) -> dict[str, Any] | None:
    """Find the one contact the user means. Returns None instead of guessing.

    Exact name/id/alias wins; otherwise a single name that contains the query
    (or is contained in it). Two candidates = no answer, never a coin flip.
    """
    needle = _norm(name)
    if not needle:
        return None
    people = list_contacts()

    def keys(person: dict[str, Any]) -> list[str]:
        found = [_norm(person.get("name")), _norm(person.get("id"))]
        found += [_norm(a) for a in person.get("aliases") or []]
        return [k for k in found if k]

    for person in people:
        if needle in keys(person):
            return person
    hits = [p for p in people if any(needle in k or k in needle for k in keys(p))]
    return hits[0] if len(hits) == 1 else None


def clean_aliases(raw: Any) -> list[str]:
    """Aliases arrive as a list or as one comma/semicolon separated string."""
    if isinstance(raw, str):
        raw = re.split(r"[,;]", raw)
    out: list[str] = []
    for item in raw or []:
        alias = str(item).strip()
        if alias and _norm(alias) not in {_norm(a) for a in out}:
            out.append(alias)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "contact"


def upsert(contact: dict[str, Any]) -> dict[str, Any]:
    """Create or update one contact. Raises ValueError on bad input."""
    name = str(contact.get("name") or "").strip()
    if not name:
        raise ValueError("A contact needs a name.")
    phone = str(contact.get("phone") or "").strip()
    if len(_digits(phone)) < 5:
        raise ValueError("A phone number needs at least 5 digits, with the country code.")
    aliases = clean_aliases(contact.get("aliases"))

    data = load()
    cid = str(contact.get("id") or "").strip() or _slug(name)
    item = {"id": cid, "name": name, "phone": phone, "aliases": aliases}
    people = data.setdefault("contacts", [])
    at = next((i for i, c in enumerate(people) if c.get("id") == cid), None)
    if at is None:
        clash = next(
            (c for c in people if _norm(c.get("name")) == _norm(name)), None
        )
        if clash is not None:
            raise ValueError(f"A contact called “{clash['name']}” already exists.")
        people.append(item)
    else:
        people[at] = item
    save(data)
    return item


def delete(contact_id: str) -> bool:
    data = load()
    before = len(data.get("contacts", []))
    data["contacts"] = [c for c in data.get("contacts", []) if c.get("id") != contact_id]
    if len(data["contacts"]) == before:
        return False
    save(data)
    return True
