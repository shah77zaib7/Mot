"""Fetch a provider's model list over HTTP (stdlib only, no litellm).

The backend calls the provider — the browser never does — so the key stays
server-side. Presets live here so the UI and the tests read one source.
"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

TIMEOUT = 8.0

# Order matters: it is the order the chips are shown in Settings > Models.
PRESETS: list[dict[str, str]] = [
    {"label": "Ollama", "name": "Ollama", "base_url": "http://localhost:11434"},
    {"label": "LM Studio", "name": "LM Studio", "base_url": "http://localhost:1234/v1"},
    {"label": "OpenRouter", "name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1"},
    {"label": "Groq", "name": "Groq", "base_url": "https://api.groq.com/openai/v1"},
    {"label": "DeepSeek", "name": "DeepSeek", "base_url": "https://api.deepseek.com/v1"},
    {"label": "NVIDIA", "name": "NVIDIA", "base_url": "https://integrate.api.nvidia.com/v1"},
    {"label": "OpenAI", "name": "OpenAI", "base_url": "https://api.openai.com/v1"},
    {"label": "Custom", "name": "", "base_url": ""},
]


class FetchError(Exception):
    """A model fetch that failed in a way the user can act on."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code  # bad_url | timeout | unreachable | auth | not_found | not_json | empty


def _port(url: str | None) -> int | None:
    try:
        return urlparse(url or "").port
    except ValueError:
        return None


def _host(url: str | None) -> str:
    try:
        return urlparse(url or "").hostname or ""
    except ValueError:
        return ""


def is_ollama_base(base_url: str | None) -> bool:
    return _port(base_url) == 11434


def is_lmstudio_base(base_url: str | None) -> bool:
    return _port(base_url) == 1234


def _candidates(base_url: str | None) -> list[str]:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise FetchError("Enter a base URL first, for example https://api.openai.com/v1.",
                         "bad_url")
    if not urlparse(base).scheme:
        raise FetchError("The base URL needs http:// or https:// in front of it.", "bad_url")
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    urls = [f"{base}/models"]
    if base.endswith("/v1"):  # some gateways only expose /models at the root
        urls.append(f"{origin}/models")
    urls.append(f"{origin}/api/tags")  # native Ollama; only tried if the others fail
    return list(dict.fromkeys(urls))


def _request(url: str, api_key: str | None) -> tuple[int, bytes]:
    headers = {"Accept": "application/json", "User-Agent": "Mot/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carries a body
        try:
            body = exc.read()
        except Exception:
            body = b""
        return int(exc.code), body
    except (socket.timeout, TimeoutError) as exc:
        raise FetchError(
            f"{_host(url) or 'The server'} took too long to answer. "
            "Check the base URL and try again.", "timeout",
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise FetchError(
                f"{_host(url) or 'The server'} took too long to answer. "
                "Check the base URL and try again.", "timeout",
            ) from exc
        if isinstance(reason, ssl.SSLError):
            raise FetchError(
                f"{_host(url)} didn't accept a secure connection. "
                "Check that the URL starts with https://.", "unreachable",
            ) from exc
        raise FetchError(
            f"Can't reach {_host(url) or url}. Check the base URL, and make sure "
            "the server is running.", "unreachable",
        ) from exc
    except ssl.SSLError as exc:
        raise FetchError(
            f"{_host(url)} didn't accept a secure connection. "
            "Check that the URL starts with https://.", "unreachable",
        ) from exc
    except ValueError as exc:
        raise FetchError(
            "That doesn't look like a URL. Use the API root, "
            "for example https://api.openai.com/v1.", "bad_url",
        ) from exc


def _looks_like_html(text: str) -> bool:
    head = text[:200].lower()
    return "<html" in head or "<!doctype" in head or "<head" in head


def _parse(body: bytes, url: str) -> list[dict[str, Any]]:
    text = body.decode("utf-8", "replace").strip()
    if not text:
        raise FetchError(f"{url} answered with an empty body.", "not_json")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        if _looks_like_html(text):
            raise FetchError(
                "That address returned a web page, not a model list. Use the API root, "
                "for example https://api.openai.com/v1.", "not_json",
            ) from exc
        raise FetchError(
            f"{url} didn't answer with JSON. Check that it is the API root, "
            "not a page on the website.", "not_json",
        ) from exc
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data["data"]  # OpenAI-style {"data": [{"id": ...}]}
    elif isinstance(data, dict) and isinstance(data.get("models"), list):
        rows = data["models"]  # Ollama /api/tags {"models": [{"name": ...}]}
    else:
        raise FetchError(
            f"{url} answered with JSON, but not a model list. "
            "Check that it is the API root.", "not_json",
        )
    return [row for row in rows if isinstance(row, dict)]


def _model_id(row: dict[str, Any]) -> str:
    value = row.get("id") or row.get("name") or row.get("model") or ""
    return str(value).strip()


def _zero(value: Any) -> bool:
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return False


def _openrouter_free(model_id: str, row: dict[str, Any]) -> bool:
    if model_id.endswith(":free"):
        return True
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return False
    return _zero(pricing.get("prompt")) and _zero(pricing.get("completion") or 0)


def tag_for(model_id: str, row: dict[str, Any], base_url: str | None, source: str) -> str:
    """free | paid | local | unknown — see docs/Phases.md Phase 1.5."""
    if source.endswith("/api/tags") or is_ollama_base(base_url) or is_lmstudio_base(base_url):
        return "local"
    if _host(base_url).endswith("openrouter.ai"):
        return "free" if _openrouter_free(model_id, row) else "paid"
    return "unknown"


def fetch_models(base_url: str | None, api_key: str | None = None) -> list[dict[str, str]]:
    """GET {base_url}/models (plus /api/tags for Ollama). Raises FetchError."""
    candidates = _candidates(base_url)
    problems: list[FetchError] = []
    for url in candidates:
        status, body = _request(url, api_key)
        if status in (401, 403):
            problems.append(FetchError(
                "That API key was rejected (401). Update the key and try again.", "auth"))
            continue
        if status == 404:
            problems.append(FetchError(
                f"No model list at {url} (404).", "not_found"))
            continue
        if status >= 400:
            problems.append(FetchError(
                f"{url} answered with HTTP {status}.", "unreachable"))
            continue
        try:
            rows = _parse(body, url)
        except FetchError as exc:
            problems.append(exc)
            continue
        models: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            model_id = _model_id(row)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            models.append({"id": model_id,
                           "tag": tag_for(model_id, row, base_url, url)})
        if models:
            return models
        problems.append(FetchError(
            "That server answered, but listed no models. You can add them by hand.",
            "empty"))

    if problems:
        for code in ("auth", "not_json", "timeout", "unreachable", "empty", "not_found"):
            match = next((p for p in problems if p.code == code), None)
            if match:
                raise match
        raise problems[0]
    raise FetchError("That server didn't answer with a model list.", "not_json")
