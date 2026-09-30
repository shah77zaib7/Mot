"""litellm wrapper: streaming chat, profile switching, friendly errors."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator

from . import config

REQUEST_TIMEOUT = 120.0


class LLMError(Exception):
    """A model error worth showing to the user, with an optional fix hint."""

    def __init__(self, message: str, fix: str | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix  # "settings" opens the Settings modal
        self.code = code  # "rate_limit" gets its own banner with a Retry button


def friendly(exc: BaseException, profile: dict[str, Any]) -> LLMError:
    """Turn a litellm/provider exception into a short, human sentence."""
    text = str(exc).lower()
    api_base = (profile.get("api_base") or "").lower()
    local = any(h in api_base for h in ("localhost", "127.0.0.1", "::1"))
    name = profile.get("name") or "this model"

    if any(
        s in text
        for s in ("connection refused", "connect call failed", "failed to establish",
                  "couldn't connect", "max retries", "connectionerror", "cannot connect")
    ):
        if local:
            return LLMError(
                f"{name} isn't reachable. Is Ollama (or your local server) running? "
                "Start it, or pick another model.",
                fix="settings",
            )
        return LLMError(
            f"Can't reach {api_base or 'the API host'}. Check the API base URL in Settings.",
            fix="settings",
        )
    if any(s in text for s in ("timed out", "timeout", "read timed out")):
        return LLMError(
            f"{name} took too long to answer. The model may still be loading — try again.",
            fix="settings",
        )
    if any(s in text for s in ("429", "rate limit", "rate_limit", "ratelimit",
                               "too many requests", "quota", "exceeded your limit",
                               "insufficient balance", "billing")):
        return LLMError(
            "The provider hit its rate limit or quota. Wait a moment and try again, "
            "or switch to another model.",
            code="rate_limit",
        )
    if any(s in text for s in ("401", "403", "unauthorized", "invalid api key",
                               "incorrect api key", "authentication", "permission denied")):
        return LLMError(
            "That API key was rejected. Update it in Settings.",
            fix="settings",
        )
    if any(s in text for s in ("missing credentials", "api_key", "api key",
                               "workload_identity", "openai_api_key")):
        return LLMError(
            f"No API key for '{name}'. Add one in Settings.",
            fix="settings",
        )
    if any(s in text for s in ("404", "not found", "does not exist", "no such model",
                               "model_not_found", "pull")):
        return LLMError(
            f"Model '{profile.get('label') or profile.get('model')}' isn't available on "
            f"{name}. Check the model list in Settings.",
            fix="settings",
        )
    if "api key" in text and profile.get("key_ref"):
        return LLMError("No API key is stored for this provider. Add one in Settings.",
                        fix="settings")

    short = " ".join(str(exc).split())[:300]
    return LLMError(f"Something went wrong talking to {name}: {short}")


def _litellm():
    import litellm  # imported lazily: keeps the window opening fast

    litellm.drop_params = True
    return litellm


async def probe_reachable(profile: dict[str, Any]) -> LLMError | None:
    """Quick TCP check so 'Ollama isn't running' appears in ~1s, not 20s."""
    api_base = profile.get("api_base")
    if not api_base:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(api_base)
        host = parsed.hostname
        if not host:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    # Skip the slow dual-stack dance on Windows.
    target = "127.0.0.1" if host == "localhost" else host
    local = host in ("localhost", "127.0.0.1", "::1")

    # Remote hosts get one quick retry: a dropped TCP connection must not turn a
    # working reply into an error. Local servers keep failing fast.
    # Remote hosts get one quick retry: a dropped TCP connection must not turn a
    # working reply into an error. Local servers keep failing fast.
    for _ in range(1 if local else 2):
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port), timeout=3.0
            )
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return None
        except Exception:  # noqa: BLE001 - unreachable either way
            pass

    name = profile.get("name") or "This model"
    if local:
        return LLMError(
            f"{name} isn't reachable. Is Ollama (or your local server) running? "
            "Start it, or pick another model.",
            fix="settings",
        )
    return LLMError(
        f"Can't reach {host}:{port}. Check the API base URL in Settings.",
        fix="settings",
    )


def _kwargs(profile: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": profile.get("model")}
    if profile.get("api_base"):
        kwargs["api_base"] = profile["api_base"]
    ref = profile.get("key_ref")
    key = config.get_secret(ref) if ref else None
    native = str(profile.get("model") or "").startswith("ollama/")
    if key:
        kwargs["api_key"] = key
    elif not native and not _is_local(profile):
        raise LLMError(
            f"No API key is stored for '{profile.get('name')}'. Add it in Settings.",
            fix="settings",
        )
    if "api_key" not in kwargs and _is_local(profile) and not native:
        # Local openai-compatible servers (LM Studio, llama.cpp) ignore the key,
        # but litellm still wants one.
        kwargs["api_key"] = "not-needed"
    return kwargs


def _is_local(profile: dict[str, Any]) -> bool:
    host = (profile.get("api_base") or "").lower()
    return any(h in host for h in ("localhost", "127.0.0.1", "::1"))


def _history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in messages if m.get("content")]


async def stream_chat(
    profile: dict[str, Any],
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Yield assistant text chunks from litellm."""
    error = await probe_reachable(profile)
    if error:
        raise error
    kwargs = _kwargs(profile)
    litellm = _litellm()
    try:
        stream = await litellm.acompletion(
            messages=_history(messages),
            stream=True,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to a friendly message
        raise friendly(exc, profile) from exc

    try:
        async for chunk in stream:
            delta = ""
            try:
                delta = chunk.choices[0].delta.content or ""
            except (AttributeError, IndexError, KeyError):
                continue
            if delta:
                yield delta
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise friendly(exc, profile) from exc

