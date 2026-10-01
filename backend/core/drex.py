"""Drex client — calibrated probabilities for a typed question (stdlib only).

Mirror of core/fetch.py: urllib, one timeout, an error class with a code the
UI can act on, and no third-party client. The key lives in the project `.env`
(see Memory.md — documented exception to the keyring-only rule); it is never
logged, never returned by an API, and never written anywhere but the header.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

BASE_URL = "https://drex.nace.ai"
MODEL = "drex-v1.5"
TIMEOUT = 15.0
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
DASHBOARD = "https://drex.nace.ai/dashboard/api-keys"

# One canned question, used by Settings > Drex → "Check connection".
CHECK_STATE = "The user asked Mot to verify its Drex connection."
CHECK_QUESTIONS: dict[str, dict[str, str]] = {
    "urgent": {"type": "noul", "instructions": "The text conveys urgency."}
}


class DrexError(Exception):
    """A Drex problem worth showing, with a short code the UI can switch on."""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _env_value(path: Path, name: str) -> str | None:
    """Read NAME from a dotenv file (hand-rolled: no python-dotenv)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            value = value.strip().strip('"').strip("'")
            return value or None
    return None


def api_key() -> str | None:
    """DREX_API_KEY from the process env, else the project `.env`."""
    key = os.environ.get("DREX_API_KEY", "").strip()
    if key:
        return key
    return _env_value(ENV_PATH, "DREX_API_KEY")


def has_key() -> bool:
    return api_key() is not None


# transport is injectable so tests never touch the network -------------------
Transport = Callable[[str, bytes], tuple[int, Any]]


def _transport(path: str, body: bytes) -> tuple[int, Any]:
    key = api_key()
    if not key:
        raise DrexError(
            "No DREX_API_KEY found. Add one to the project .env file — "
            f"create it at {DASHBOARD}.",
            "no_key",
        )
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a body
        raw = exc.read()
        status = int(exc.code)
    except TimeoutError as exc:
        raise DrexError("Drex took too long to answer. Try again.", "timeout") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise DrexError("Drex took too long to answer. Try again.", "timeout") from exc
        raise DrexError(f"Couldn't reach Drex at {BASE_URL}.", "unreachable") from exc
    except OSError as exc:
        raise DrexError(f"Couldn't reach Drex at {BASE_URL}.", "unreachable") from exc

    try:
        return status, json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError) as exc:
        raise DrexError("Drex sent a response Mot couldn't read.", "bad_response") from exc


def ask(
    state: str,
    questions: dict[str, dict[str, Any]],
    transport: Transport = _transport,
) -> dict[str, Any]:
    """POST /v1/systemone → the raw answer object (answers, usage, model…)."""
    if not questions:
        raise DrexError("Drex needs at least one question.", "bad_request")
    body = json.dumps(
        {"model": MODEL, "state": state, "questions": questions},
        ensure_ascii=False,
    ).encode("utf-8")

    status, data = transport("/v1/systemone", body)

    if status in (401, 403):
        raise DrexError(
            f"Drex rejected the API key. Get a new one at {DASHBOARD}.", "auth"
        )
    if status == 404:
        raise DrexError("Drex doesn't know this endpoint.", "bad_request")
    if status == 429:
        raise DrexError("Drex is rate limiting Mot right now. Try again shortly.", "busy")
    if status >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        hint = f" {detail}" if isinstance(detail, str) else ""
        raise DrexError(f"Drex refused the request.{hint}", "bad_request")
    if not isinstance(data, dict):
        raise DrexError("Drex sent a response Mot couldn't read.", "bad_response")
    return data


def check(transport: Transport = _transport) -> dict[str, Any]:
    """One canned round trip → {ok, noul, ms} for the Settings check button."""
    started = time.perf_counter()
    data = ask(CHECK_STATE, CHECK_QUESTIONS, transport=transport)
    ms = int(round((time.perf_counter() - started) * 1000))

    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    first = next(iter(answers.values()), {}) if answers else {}
    noul = first.get("noul")
    if not isinstance(noul, (int, float)):
        raise DrexError("Drex answered without a probability.", "bad_response")
    return {
        "ok": True,
        "noul": round(float(noul), 4),
        "ms": ms,
        "model": data.get("model") or MODEL,
        "has_key": True,
    }
