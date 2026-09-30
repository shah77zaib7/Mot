"""Settings > Routines: the ordered step editor."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import routines

router = APIRouter(prefix="/api", tags=["routines"])


class RoutineIn(BaseModel):
    id: str | None = None
    name: str
    steps: list[dict[str, Any]] = []


@router.get("/routines")
def list_routines() -> dict[str, Any]:
    return {"routines": routines.list_routines()}


@router.post("/routines")
def save_routine(body: RoutineIn) -> dict[str, Any]:
    try:
        routine = routines.upsert(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"routine": routine, "routines": routines.list_routines()}


@router.delete("/routines")
def delete_routine(id: str) -> dict[str, Any]:  # noqa: A002 - query param name
    if not routines.delete(id):
        raise HTTPException(404, "Routine not found.")
    return {"ok": True, "routines": routines.list_routines()}
