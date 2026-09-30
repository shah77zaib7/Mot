"""Chat history CRUD."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import config, db

router = APIRouter(prefix="/api", tags=["chats"])


class NewChatIn(BaseModel):
    title: str | None = None
    profile: str | None = None


@router.get("/chats")
def list_chats() -> dict:
    return {"chats": db.list_chats()}


@router.post("/chats")
def create_chat(body: NewChatIn | None = None) -> dict:
    body = body or NewChatIn()
    profile = body.profile or config.active_label()
    return {"chat": db.create_chat(profile=profile, title=body.title or "New chat")}


@router.get("/chats/{chat_id}")
def read_chat(chat_id: str) -> dict:
    chat = db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(404, "Chat not found.")
    return {"chat": chat, "messages": db.get_messages(chat_id)}


@router.delete("/chats/{chat_id}")
def remove_chat(chat_id: str) -> dict:
    if not db.delete_chat(chat_id):
        raise HTTPException(404, "Chat not found.")
    return {"ok": True}
