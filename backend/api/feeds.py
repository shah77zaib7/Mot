"""Settings > Feeds — feed lists, the background refresh, POST one URL to test."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..core import feeds, ingest, snapshot

router = APIRouter(prefix="/api", tags=["feeds"])
log = logging.getLogger("mot")


class FeedsIn(BaseModel):
    topics: dict[str, list[str]] = Field(default_factory=dict)


class TestIn(BaseModel):
    url: str


class IngestIn(BaseModel):
    enabled: bool | None = None
    interval_hours: float | None = None


@router.get("/feeds")
async def get_feeds() -> dict:
    return {
        "topics": feeds.load(),
        "defaults": feeds.DEFAULTS,
        "aliases": feeds.ALIASES,
        "ingest": ingest.status(),
        "sources": [
            {"url": url, "error": reason} for url, reason in snapshot.sources().items()
        ],
    }


@router.put("/feeds/ingest")
async def put_ingest(body: IngestIn) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    log.info("feed refresh settings: %s", patch)
    return {"ok": True, "ingest": ingest.save(patch)}


@router.post("/feeds/refresh")
async def refresh_feeds() -> dict:
    """Run one refresh now; it is bounded by the 8 s per-source deadline."""
    run = await asyncio.to_thread(ingest.refresh_now)
    return {**run, "ingest": ingest.status()}


@router.put("/feeds")
async def put_feeds(body: FeedsIn) -> dict:
    clean: dict[str, list[str]] = {}
    for topic, urls in body.topics.items():
        name = str(topic).strip().lower()
        if not name:
            continue
        if not isinstance(urls, list):
            return {"ok": False, "message": f"Feeds for {name} must be a list."}
        good = [str(u).strip() for u in urls if str(u).strip()]
        bad = [u for u in good if not u.startswith(("http://", "https://"))]
        if bad:
            return {"ok": False, "message": f"{bad[0]} isn't an http(s) URL."}
        if good:
            clean[name] = good
    if not clean:
        return {"ok": False, "message": "Keep at least one feed."}
    try:
        feeds.save(clean)
    except OSError:
        return {"ok": False, "message": "Couldn't write data/feeds.json. Check the folder."}
    log.info("feeds saved: %s", {k: len(v) for k, v in clean.items()})
    return {"ok": True, "message": "Feeds saved.", "topics": feeds.load()}


@router.post("/feeds/test")
async def test_feed(body: TestIn) -> dict:
    return feeds.test_feed(body.url)
