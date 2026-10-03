"""Providers and their models (Settings > Models)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import config, fallback, fetch

router = APIRouter(prefix="/api", tags=["settings"])


class ModelIn(BaseModel):
    id: str
    tag: str = "unknown"
    tag_locked: bool = False


class ProviderIn(BaseModel):
    id: str | None = None
    name: str
    base_url: str = ""
    api_key: str | None = None  # write-only, never returned
    models: list[ModelIn] = []


class ActiveIn(BaseModel):
    provider_id: str
    model_id: str


class FetchIn(BaseModel):
    base_url: str
    api_key: str | None = None


class ThemeIn(BaseModel):
    theme: str | None = None
    accent: str | None = None


class FallbackIn(BaseModel):
    models: list[dict] = []


class WakeIn(BaseModel):
    provider_id: str
    model_id: str


def _active() -> dict[str, Any] | None:
    resolved = config.active_model()
    if resolved is None:
        return None
    return {"provider_id": resolved["provider_id"], "model_id": resolved["model_id"]}


@router.get("/providers")
def get_providers() -> dict:
    cfg = config.load()
    return {
        "providers": config.list_providers(),
        "active": _active(),
        "theme": cfg.get("theme", "system"),
        "accent": config.accent(),
        "fallback": config.fallback_list(),
        "resting": fallback.resting(),
        "presets": fetch.PRESETS,
    }


@router.post("/providers")
def save_provider(body: ProviderIn) -> dict:
    try:
        provider = config.save_provider(body.model_dump(), body.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"provider": provider, "active": _active()}


@router.delete("/providers")
def delete_provider(pid: str) -> dict:
    if not config.delete_provider(pid):
        raise HTTPException(404, "Provider not found.")
    return {"ok": True, "active": _active()}


@router.put("/providers/active")
def set_active(body: ActiveIn) -> dict:
    if not config.set_active(body.provider_id, body.model_id):
        raise HTTPException(404, "That model isn't saved any more. Fetch models again.")
    return {"active": _active()}


@router.post("/providers/wake")
def wake_model(body: WakeIn) -> dict:
    """Hand-picking a resting model ends its cooldown right away."""
    fallback.wake(body.provider_id, body.model_id)
    return {"resting": fallback.resting()}


@router.post("/providers/fetch")
async def fetch_models(body: FetchIn) -> dict:
    """Ask the provider for its model list. The browser never calls it."""
    try:
        models = await asyncio.to_thread(fetch.fetch_models, body.base_url, body.api_key)
    except fetch.FetchError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    except Exception as exc:  # noqa: BLE001 - show something friendly, never a traceback
        return {"ok": False, "code": "unreachable",
                "message": "That address didn't work: " + " ".join(str(exc).split())[:200]}
    return {"ok": True, "models": models}


@router.put("/settings")
def update_settings(body: ThemeIn) -> dict:
    """Both fields are optional: the UI sends whichever one just changed."""
    if body.theme is not None:
        config.set_theme(body.theme)
    if body.accent is not None:
        config.set_accent(body.accent)
    cfg = config.load()
    return {"theme": cfg.get("theme", "system"), "accent": config.accent()}


@router.put("/fallback")
def update_fallback(body: FallbackIn) -> dict:
    """Save the auto-switch order and its 'allow auto-switch' ticks."""
    return {"fallback": config.set_fallback(body.models)}
