"""Settings > Contacts: name, phone number, aliases."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import contacts

router = APIRouter(prefix="/api", tags=["contacts"])


class ContactIn(BaseModel):
    id: str | None = None
    name: str
    phone: str = ""
    aliases: list[str] | str = []


@router.get("/contacts")
def list_contacts() -> dict[str, Any]:
    return {"contacts": contacts.list_contacts()}


@router.post("/contacts")
def save_contact(body: ContactIn) -> dict[str, Any]:
    try:
        contact = contacts.upsert(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"contact": contact, "contacts": contacts.list_contacts()}


@router.delete("/contacts")
def delete_contact(id: str) -> dict[str, Any]:  # noqa: A002 - query param name
    if not contacts.delete(id):
        raise HTTPException(404, "Contact not found.")
    return {"ok": True, "contacts": contacts.list_contacts()}
