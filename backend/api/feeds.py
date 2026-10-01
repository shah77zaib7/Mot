"""Settings > Feeds — GET/PUT the topic feed lists, POST one URL to test it."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..core import feeds

router = APIRouter(prefix="/api", tags=["feeds"])
log = logging.getLogger("mot")


class FeedsIn(BaseModel):
    topics: dict[str, list[str]] = Field(default_factory=dict)


class TestIn(BaseModel):
    url: str


@router.get("/feeds")
async def get_feeds() -> dict:
    return {"topics": feeds.load(), "defaults": feeds.DEFAULTS, "aliases": feeds.ALIASES}


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
