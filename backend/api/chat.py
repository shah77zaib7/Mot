"""Streaming chat (SSE) — POST /api/chat."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core import config, db, fallback, llm, llm_router, router as fast, runner

router = APIRouter(prefix="/api", tags=["chat"])

HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# chat_id -> Event set by the Stop button (loopback sockets drop silently)
_STOP_EVENTS: dict[str, "asyncio.Event"] = {}

log = logging.getLogger("mot")


@router.post("/chat/stop")
async def stop_chat(body: StopIn) -> dict:
    event = _STOP_EVENTS.get(body.chat_id)
    if event is not None:
        event.set()
    return {"ok": True}


class ChatIn(BaseModel):
    message: str = ""
    chat_id: str | None = None
    provider_id: str | None = None  # provider picked in the model dropdown
    model_id: str | None = None
    regenerate: bool = False  # re-run the last user message
    findings: list[dict] | None = None  # Summarize button: headlines to answer from


class StopIn(BaseModel):
    chat_id: str


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _history(chat_id: str) -> list[dict[str, str]]:
    return [
        {"role": m["role"], "content": m["content"]}
        for m in db.get_messages(chat_id)
        if m["role"] in ("user", "assistant")
    ]


def _chunks(text: str, size: int = 60) -> list[str]:
    """A finished reply in small pieces, so the cursor still animates."""
    return [text[i:i + size] for i in range(0, len(text), size)]


async def _action_events(
    steps: list[dict[str, Any]],
    chat_id: str,
    collected: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Run steps off the event loop and stream one action card per step."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(action: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, action)

    def work() -> None:
        try:
            collected.extend(runner.run_steps(steps, emit, chat_id))
        except Exception:  # noqa: BLE001 - a tool bug must not hang the stream
            logging.getLogger("mot").exception("Tool run failed")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=work, daemon=True).start()

    while True:
        action = await queue.get()
        if action is None:
            break
        yield _event({"type": "action", "action": action})


async def _fast_stream(
    text: str,
    plan: list[dict[str, Any]],
    chat_id: str | None,
    label: str,
    add_user: bool = True,
) -> AsyncIterator[str]:
    """Run a fast-path command: no model, action cards stream live."""
    if chat_id is None or db.get_chat(chat_id) is None:
        chat = db.create_chat(profile=label, title=db.title_from(text))
        chat_id = chat["id"]
    elif not db.get_messages(chat_id):
        db.touch_chat(chat_id, title=db.title_from(text), profile=label)
    if add_user:  # regenerate re-runs the steps for the message already saved
        db.add_message(chat_id, "user", text, label)

    yield _event({"type": "start", "chat_id": chat_id, "profile": label})

    collected: list[dict[str, Any]] = []
    async for event in _action_events(plan, chat_id, collected):
        yield event

    content = runner.summary(collected)
    message = db.add_message(chat_id, "assistant", content, label, actions=collected)
    yield _event(
        {"type": "done", "chat_id": chat_id, "message_id": message["id"],
         "profile": label, "text": content, "actions": collected}
    )


@router.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    text = body.message.strip()
    if not text and not body.regenerate:
        raise HTTPException(400, "Message is empty.")

    regen_id = body.chat_id
    if body.regenerate and (regen_id is None or db.get_chat(regen_id) is None):
        raise HTTPException(400, "There is no message to regenerate.")

    # Fast path first: "open X", "search Y on YouTube", "run <routine>" — no LLM.
    # Regenerate parses too: re-running "Gold news today" must bring the card
    # back instead of a plain reply from a model with no tools in its hands.
    plan: list[dict[str, Any]] = []
    rest: list[str] = []
    if not body.findings:
        plan, rest = fast.parse_parts(text)
    if not plan and rest and not body.findings:
        net = fast.news_steps(text)  # safety net: a news request is never plain chat
        if net and len(rest) == 1:
            log.info("path=fast steps=%s (safety net)", [s.get("action") for s in net])
            if body.regenerate:
                db.drop_last_assistant(regen_id)  # type: ignore[arg-type]
            label = config.active_label() or "Mot"
            return StreamingResponse(
                _fast_stream(text, net, regen_id, label, add_user=not body.regenerate),
                media_type="text/event-stream",
                headers=HEADERS,
            )
        plan = net or plan  # mixed message: the card first, the model gets the rest

    if plan and not rest:
        log.info("path=fast steps=%s", [s.get("action") for s in plan])
        if body.regenerate:
            db.drop_last_assistant(regen_id)  # type: ignore[arg-type]
        label = config.active_label() or "Mot"
        return StreamingResponse(
            _fast_stream(text, plan, regen_id, label, add_user=not body.regenerate),
            media_type="text/event-stream",
            headers=HEADERS,
        )

    target = config.chat_target(body.provider_id, body.model_id)
    if target is None:
        raise HTTPException(
            400, "No model chosen. Open Settings and add a provider with a model."
        )
    label = target["label"]

    chat_id = body.chat_id
    if body.regenerate:
        if chat_id is None or db.get_chat(chat_id) is None:
            raise HTTPException(400, "There is no message to regenerate.")
        db.drop_last_assistant(chat_id)  # replace the previous reply
    else:
        if chat_id is None or db.get_chat(chat_id) is None:
            chat = db.create_chat(profile=label, title=db.title_from(text))
            chat_id = chat["id"]
        elif not db.get_messages(chat_id):
            db.touch_chat(chat_id, title=db.title_from(text), profile=label)
        db.add_message(chat_id, "user", text, label)

    history = _history(chat_id)
    stop_event = asyncio.Event()
    _STOP_EVENTS[chat_id] = stop_event
    route_text = " and ".join(rest) if plan else text  # only what the rules couldn't take

    async def stream() -> AsyncIterator[str]:
        nonlocal label, target  # a fallback switch renames the model mid-reply
        yield _event({"type": "start", "chat_id": chat_id, "profile": label})
        collected: list[dict[str, Any]] = []  # action cards: fast steps + model steps
        parts: list[str] = []
        saved = False
        researched = False  # True once findings were answered from, not routed

        def compose() -> str:
            reply = "".join(parts)
            if not reply:  # research or stream failed: keep the cards' own line
                return runner.summary(collected) if collected else ""
            if researched:
                return reply  # bullets stand alone; the cards are above them
            summary = runner.summary(collected) if collected else ""
            if summary:
                return f"{summary} {reply}"
            return reply

        async def speak(profiles: list[dict[str, Any]],
                        messages: list[dict[str, Any]]) -> AsyncIterator[str]:
            """Deltas, plus a short notice each time the router changes model."""
            async for kind, text in fallback.stream(profiles, messages):
                if kind == "notice":
                    yield _event({"type": "switch", "text": text})
                    continue
                if stop_event.is_set():
                    break
                parts.append(text)
                yield _event({"type": "delta", "text": text})

        async def research(items: list[dict[str, Any]]) -> AsyncIterator[str]:
            """Second completion: findings in, 4-6 sourced bullets out."""
            nonlocal researched
            researched = True
            log.info("path=research items=%d", len(items))
            messages = llm_router.research_messages(route_text, history, items)
            async for event in speak(fallback.candidates(target), messages):
                yield event
            if parts and not stop_event.is_set():
                footer = llm_router.research_footer()
                parts.append(footer)
                yield _event({"type": "delta", "text": footer})

        try:
            decision: dict[str, Any] = {"kind": "chat"}
            if body.findings:
                # Summarize button: headlines already on screen, no routing.
                async for event in research(list(body.findings)):
                    yield event
            else:
                if plan:
                    # mixed message: the rules did their part, the model gets the rest
                    log.info("path=fast(+llm) steps=%s", [s.get("action") for s in plan])
                    async for event in _action_events(plan, chat_id, collected):
                        yield event

                if rest:
                    # One pass over the ordered list: the first model that
                    # answers wins, the others are cooled down (Phase 6).
                    out = await fallback.route(
                        fallback.candidates(target),
                        route_text,
                        history,
                        done=runner.summary(collected) if collected else None,
                    )
                    for text in out["notices"]:
                        yield _event({"type": "switch", "text": text})
                    decision = out["decision"]
                    target = out["profile"]
                    label = target["label"]
                    if decision["kind"] == "chat":
                        log.info("path=llm->chat (%s)", decision.get("reason"))

                if decision["kind"] == "steps":
                    async for event in _action_events(decision["steps"], chat_id, collected):
                        yield event
                    items = llm_router.findings_from(collected)
                    if items:
                        # Research tools ran: answer from them, never from memory.
                        async for event in research(items):
                            yield event
                        decision = {"kind": "chat"}
                if decision["kind"] == "reply":
                    for chunk in _chunks(decision["text"]):
                        if stop_event.is_set():  # Stop pressed: keep what we have
                            break
                        parts.append(chunk)
                        yield _event({"type": "delta", "text": chunk})
                elif decision["kind"] == "chat" and not researched:
                    async for event in speak(fallback.candidates(target), history):
                        yield event
        except llm.LLMError as exc:
            content = compose()
            if content:
                db.add_message(chat_id, "assistant", content, label,
                               actions=collected or None)
                saved = True
            yield _event(
                {"type": "error", "message": exc.message, "fix": exc.fix,
                 "code": exc.code, "model": label, "chat_id": chat_id,
                 "models": exc.models}
            )
        except Exception:  # noqa: BLE001 - never crash the stream
            content = compose()
            if content:
                db.add_message(chat_id, "assistant", content, label,
                               actions=collected or None)
                saved = True
            yield _event(
                {"type": "error", "message": "The reply was interrupted. Try again.",
                 "chat_id": chat_id}
            )
        else:
            content = compose()
            if content:
                message = db.add_message(chat_id, "assistant", content, label,
                                         actions=collected or None)
                saved = True
                yield _event(
                    {"type": "done", "chat_id": chat_id, "message_id": message["id"],
                     "profile": label, "text": content, "actions": collected}
                )
            elif not stop_event.is_set():
                yield _event(
                    {"type": "error",
                     "message": "The model returned an empty reply. Try again.",
                     "chat_id": chat_id}
                )
        finally:
            _STOP_EVENTS.pop(chat_id, None)
            # Client pressed Stop: keep whatever text already arrived.
            if not saved and compose():
                db.add_message(chat_id, "assistant", compose(), label,
                               actions=collected or None)

    return StreamingResponse(stream(), media_type="text/event-stream", headers=HEADERS)
