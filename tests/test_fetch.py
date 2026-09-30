"""Model fetching: mock servers for the happy paths and every friendly error."""
from __future__ import annotations

import json

import pytest

from backend.core import fetch


def test_openai_style_models_list(serve):
    payload = json.dumps({"data": [{"id": "alpha-1"}, {"id": "beta-2"}]})
    base = serve({"/v1/models": (200, payload)})

    models = fetch.fetch_models(f"{base}/v1")

    assert [m["id"] for m in models] == ["alpha-1", "beta-2"]
    assert all(m["tag"] == "unknown" for m in models)


def test_sends_the_key_as_bearer(serve):
    seen: list = []
    base = serve(
        {"/v1/models": (200, '{"data":[{"id":"m"}]}')},
        seen=seen,
    )

    fetch.fetch_models(f"{base}/v1", api_key="sk-test-123")

    assert seen and seen[0][1] == "Bearer sk-test-123"


def test_ollama_falls_back_to_api_tags(serve):
    base = serve({
        "/models": (404, "nope"),
        "/api/tags": (200, json.dumps({"models": [{"name": "qwen2.5:7b"},
                                                   {"name": "llama3.2:3b"}]})),
    })

    models = fetch.fetch_models(base)

    assert [m["id"] for m in models] == ["qwen2.5:7b", "llama3.2:3b"]
    assert all(m["tag"] == "local" for m in models)


def test_bad_key_is_a_friendly_auth_error(serve):
    base = serve({"/v1/models": (401, '{"error":"invalid api key"}')})

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(f"{base}/v1", api_key="sk-wrong")

    assert exc.value.code == "auth"
    assert "401" in exc.value.message


def test_timeout_is_friendly(serve, monkeypatch):
    monkeypatch.setattr(fetch, "TIMEOUT", 0.5)
    base = serve({"/v1/models": (200, '{"data":[]}')}, delay=3)

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(f"{base}/v1")

    assert exc.value.code == "timeout"
    assert "too long" in exc.value.message


def test_html_answer_is_explained(serve):
    base = serve({"/models": (200, "<html><head><title>Welcome</title></head></html>")})

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(base)

    assert exc.value.code == "not_json"
    assert "web page" in exc.value.message


def test_missing_endpoint_says_add_manually(serve):
    base = serve({})  # every path 404s

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(f"{base}/v1")

    assert exc.value.code == "not_found"


def test_unreachable_host(serve):
    base = serve({})
    dead = f"{base.rsplit(':', 1)[0]}:1"  # nothing listens on port 1

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(dead)

    assert exc.value.code == "unreachable"


def test_url_without_scheme(serve):  # noqa: ARG001 - documents that no request is made
    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models("api.openai.com/v1")

    assert exc.value.code == "bad_url"


def test_empty_model_list(serve):
    base = serve({"/v1/models": (200, '{"data":[]}')})

    with pytest.raises(fetch.FetchError) as exc:
        fetch.fetch_models(f"{base}/v1")

    assert exc.value.code == "empty"


# --- tags -------------------------------------------------------------------

def test_openrouter_tags():
    free_by_id = {"id": "meta-llama/llama-3.3-70b-instruct:free"}
    free_by_price = {"id": "openai/gpt-4o-mini",
                     "pricing": {"prompt": "0", "completion": "0"}}
    paid = {"id": "openai/gpt-4o", "pricing": {"prompt": "0.0000025",
                                               "completion": "0.00001"}}
    base = "https://openrouter.ai/api/v1"

    assert fetch.tag_for(free_by_id["id"], free_by_id, base, base) == "free"
    assert fetch.tag_for(free_by_price["id"], free_by_price, base, base) == "free"
    assert fetch.tag_for(paid["id"], paid, base, base) == "paid"


def test_local_and_unknown_tags():
    assert fetch.tag_for("qwen2.5:7b", {}, "http://localhost:11434",
                         "http://localhost:11434/models") == "local"
    assert fetch.tag_for("llama-3.1-8b-instant", {}, "http://localhost:1234/v1",
                         "http://localhost:1234/v1/models") == "local"
    assert fetch.tag_for("gpt-4o-mini", {}, "https://api.openai.com/v1",
                         "https://api.openai.com/v1/models") == "unknown"
