"""Ordered model fallback (Phase 6): one pass per request, with cooldowns.

The list lives in data/config.json (`fallback`); each entry is ticked with
`allow auto-switch`. On 429 / timeout / 5xx / 404 / 401 the router moves to
the next ticked model and puts the failed one out of rotation for a while.

Nothing here loops: a request walks the list exactly once and then gives up
with a message naming every model and why it failed.
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from . import config, llm, llm_router

log = logging.getLogger("mot")

# Failure kind -> seconds out of rotation. 0 means "switch, but don't rest it".
COOLDOWN: dict[str, int] = {
    "rate_limit": 5 * 60,
    "timeout": 30 * 60,
    "server": 30 * 60,
    "not_found": 6 * 60 * 60,
    "key_invalid": 0,
}

REASON: dict[str, str] = {
    "rate_limit": "rate limit",
    "timeout": "too slow",
    "server": "server error",
    "not_found": "not available",
    "key_invalid": "key invalid",
}

VERB: dict[str, str] = {
    "rate_limit": "hit its limit",
    "timeout": "took too long",
    "server": "had a server error",
    "not_found": "isn't available",
    "key_invalid": "has an invalid key",
}

# "provider_id|model_id" -> (kind, until when). Lives for this run only: a
# restart starts every model fresh, which is what a user would expect.
_COOLING: dict[str, tuple[str, float]] = {}


def key_of(profile: dict[str, Any]) -> str:
    return f"{profile.get('provider_id')}|{profile.get('model_id')}"


def classify(err: llm.LLMError) -> str | None:
    """The cooldown kind for an error, or None when we must not switch away."""
    kind = getattr(err, "kind", None)
    return kind if kind in COOLDOWN else None


def fail(profile: dict[str, Any], kind: str) -> None:
    seconds = COOLDOWN.get(kind, 0)
    if seconds <= 0:
        return
    _COOLING[key_of(profile)] = (kind, time.time() + seconds)
    log.warning("cooldown %s for %ss (%s)", profile.get("label"), seconds, kind)


def _cooling(key: str) -> bool:
    entry = _COOLING.get(key)
    if entry is None:
        return False
    if entry[1] <= time.time():
        _COOLING.pop(key, None)
        return False
    return True


def resting() -> list[dict[str, Any]]:
    """Models currently out of rotation, with the seconds left (for the UI)."""
    now = time.time()
    out: list[dict[str, Any]] = []
    for key, (kind, until) in list(_COOLING.items()):
        left = until - now
        if left <= 0:
            _COOLING.pop(key, None)
            continue
        provider_id, model_id = key.split("|", 1)
        out.append({
            "provider_id": provider_id,
            "model_id": model_id,
            "reason": REASON.get(kind, kind),
            "seconds": int(left) + 1,
        })
    return out


def clear() -> None:
    """Testing hook: forget every cooldown."""
    _COOLING.clear()


def wake(provider_id: str, model_id: str) -> bool:
    """A hand-picked model is used at once: the cooldown only filters
    automatic moves (manual switching must always work)."""
    return _COOLING.pop(f"{provider_id}|{model_id}", None) is not None


def candidates(target: dict[str, Any]) -> list[dict[str, Any]]:
    """The requested model first, then the ticked, resting-free list, once."""
    out: list[dict[str, Any]] = []
    first = key_of(target)
    if _cooling(first):
        log.info("model %s is resting -> skipped this request", target.get("label"))
    else:
        out.append(target)
    for entry in config.fallback_list():
        key = f"{entry['provider_id']}|{entry['model_id']}"
        if key == first or not entry["auto"] or _cooling(key):
            continue
        profile = config.chat_target(entry["provider_id"], entry["model_id"])
        if profile is not None:
            out.append(profile)
    return out or [target]  # one model left: it is tried even while resting


def _next_usable(profiles: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    for candidate in profiles[index + 1:]:
        if not _cooling(key_of(candidate)):
            return candidate
    return None


def notice(failed: dict[str, Any], next_one: dict[str, Any], kind: str) -> str:
    """`"qwen hit its limit, switched to llama"` — short, names both models."""
    return f"{failed['label']} {VERB.get(kind, 'failed')}, switched to {next_one['label']}"


def exhausted(attempts: list[dict[str, Any]]) -> llm.LLMError:
    items = [
        {"label": a["profile"]["label"], "why": REASON.get(a["kind"], a["kind"])}
        for a in attempts
    ]
    listing = "; ".join(f"{item['label']} — {item['why']}" for item in items)
    return llm.LLMError(
        f"No model answered just now ({listing}). Press Retry, or change the "
        "order in Settings > Models.",
        code="fallback_exhausted",
        models=items,
    )


def _record(
    attempts: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    index: int,
    profile: dict[str, Any],
    kind: str,
) -> str | None:
    """Note the failure, cool the model down, say where we're going next."""
    fail(profile, kind)
    attempts.append({"profile": profile, "kind": kind})
    log.warning("model %s failed (%s) -> next in line", profile.get("label"), kind)
    next_one = _next_usable(profiles, index)
    if next_one is None:
        return None
    _adopt(next_one)  # save it, so the model picker agrees with the reply
    return notice(profile, next_one, kind)


def _adopt(profile: dict[str, Any]) -> None:
    """Make the model we switched to the selected one.

    Without this the reply comes from model B while Settings and the picker
    still show model A, and the next refresh of `GET /api/providers` puts A
    back on screen. A save that fails must never break a reply that already
    worked, so it only logs.
    """
    try:
        saved = config.set_active(profile.get("provider_id") or "",
                                  profile.get("model_id") or "")
    except Exception:  # noqa: BLE001 - a config write must not lose the reply
        log.warning("could not save the switched model", exc_info=True)
        return
    if saved:
        log.info("active model is now %s", profile.get("label"))


async def route(
    profiles: list[dict[str, Any]],
    text: str,
    history: list[dict[str, str]],
    done: str | None = None,
) -> dict[str, Any]:
    """First model that answers wins -> {"decision", "profile", "notices"}."""
    attempts: list[dict[str, Any]] = []
    notices: list[str] = []
    for index, profile in enumerate(profiles):
        try:
            decision = await llm_router.route(profile, text, history, done=done)
        except llm.LLMError as exc:
            kind = classify(exc)
            if kind is None:
                raise  # not a switchable failure — show it as it always was
            moved = _record(attempts, profiles, index, profile, kind)
            if moved:
                notices.append(moved)
            continue
        log.info("route chose %s after %d failed attempt(s)",
                 profile.get("label"), len(attempts))
        return {"decision": decision, "profile": profile, "notices": notices}
    raise exhausted(attempts)


async def stream(
    profiles: list[dict[str, Any]],
    messages: list[dict[str, str]],
) -> AsyncIterator[tuple[str, str]]:
    """Yield ("notice", text) or ("delta", text). One pass; never switch once
    part of a reply is already on screen, or the text would splice together."""
    attempts: list[dict[str, Any]] = []
    started = False
    for index, profile in enumerate(profiles):
        try:
            async for chunk in llm.stream_chat(profile, messages):
                started = True
                yield "delta", chunk
        except llm.LLMError as exc:
            if started:
                raise
            kind = classify(exc)
            if kind is None:
                raise
            moved = _record(attempts, profiles, index, profile, kind)
            if moved:
                yield "notice", moved
            continue
        return
    raise exhausted(attempts)
