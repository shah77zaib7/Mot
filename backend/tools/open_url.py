"""open_url — open a website in the (preferred or default) browser."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..core import apps
from . import launch
from .registry import register


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not urlparse(url).scheme:
        return "https://" + url.lstrip("/")
    return url


def label_for(url: str) -> str:
    host = urlparse(url).hostname or url
    return host.removeprefix("www.")


@register(
    "open_url",
    "Open a website in the user's browser. Use only for real websites or URLs \u2014 "
    "or when open_app finds no installed app (e.g. youtube.com, tradingview.com).",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "URL to open"}},
        "required": ["url"],
    },
)
def open_url(args: dict[str, Any]) -> dict[str, Any]:
    url = normalize_url(args.get("url") or "")
    if not url:
        return {"ok": False, "message": "There is no URL to open.", "data": {}}
    result = launch.open_url(url, browser=apps.browser())
    if not result.get("ok"):
        return {"ok": False, "message": f"Couldn't open {label_for(url)}.", "data": {"url": url}}
    data: dict[str, Any] = {"url": url, "label": label_for(url)}
    if result.get("fallback"):
        data["note"] = (
            f"{result['fallback'].title()} isn't installed — used your default browser instead."
        )
    return {"ok": True, "message": f"Opened {data['label']}.", "data": data}
