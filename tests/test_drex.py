"""core/drex.py + POST /api/drex/check — the Settings check button."""
from __future__ import annotations

import json

import pytest

from backend.core import drex

ANSWER = {
    "model": "drex-v1.5",
    "answers": {"urgent": {"noul": 0.9349}},
    "usage": {"credits": 1},
    "evaluation_time_ms": 8.5,
}


def fake(transport, status=200, payload=None):
    """A transport that records what Mot sent and answers with `payload`."""
    seen: dict = {"path": None, "body": None, "auth": None}

    def _call(path: str, body: bytes) -> tuple[int, object]:
        seen["path"] = path
        seen["body"] = json.loads(body)
        return status, ANSWER if payload is None else payload

    return _call, seen


def test_check_reports_probability_and_latency(monkeypatch):
    transport, seen = fake(None)

    result = drex.check(transport=transport)

    assert result["ok"] is True
    assert result["noul"] == pytest.approx(0.9349, abs=0.001)
    assert result["ms"] >= 0
    assert seen["path"] == "/v1/systemone"
    assert seen["body"]["model"] == "drex-v1.5"
    assert seen["body"]["questions"]["urgent"]["type"] == "noul"


def test_the_key_only_ever_lives_in_the_header(monkeypatch, tmp_path):
    key = "nace_sk_" + "x" * 40
    monkeypatch.setenv("DREX_API_KEY", key)
    seen: list = []

    def transport(path, body):  # noqa: ARG001
        seen.append(body)
        return 200, ANSWER

    # ask() never receives the key: the transport adds it, the payload does not
    drex.ask("state", {"q": {"type": "noul", "instructions": "x"}}, transport=transport)
    assert key.encode() not in seen[0]


def test_the_real_transport_sends_the_key_as_bearer(monkeypatch, serve):
    key = "nace_sk_" + "y" * 40
    monkeypatch.setenv("DREX_API_KEY", key)
    auth: list = []
    base = serve({"/v1/systemone": (200, json.dumps(ANSWER))}, seen=auth)
    monkeypatch.setattr(drex, "BASE_URL", base)

    result = drex.check()

    assert result["ok"] is True
    assert auth == [("/v1/systemone", f"Bearer {key}")]


def test_env_file_is_read_when_the_process_has_no_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DREX_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comment\nDREX_API_KEY=nace_sk_abc123\n", encoding="utf-8")
    monkeypatch.setattr(drex, "ENV_PATH", env)

    assert drex.api_key() == "nace_sk_abc123"
    assert drex.has_key() is True


def test_no_key_anywhere_is_a_helpful_error(monkeypatch, tmp_path):
    monkeypatch.delenv("DREX_API_KEY", raising=False)
    monkeypatch.setattr(drex, "ENV_PATH", tmp_path / "nope.env")

    with pytest.raises(drex.DrexError) as exc:
        drex.check()

    assert exc.value.code == "no_key"
    assert "dashboard/api-keys" in exc.value.message
    assert "nace_sk" not in exc.value.message


@pytest.mark.parametrize("status,code", [(401, "auth"), (403, "auth"), (429, "busy")])
def test_http_errors_have_short_codes(status, code):
    transport, _ = fake(None, status=status)

    with pytest.raises(drex.DrexError) as exc:
        drex.check(transport=transport)
    assert exc.value.code == code


def test_an_answer_without_a_probability_is_not_a_success():
    transport, _ = fake(None, payload={"model": "drex-v1.5", "answers": {}})

    with pytest.raises(drex.DrexError) as exc:
        drex.check(transport=transport)
    assert exc.value.code == "bad_response"


def test_json_garbage_is_explained_not_raised(monkeypatch, tmp_path, serve):
    base = serve({"/v1/systemone": (200, "<html>nope</html>")})
    monkeypatch.setattr(drex, "BASE_URL", base)
    monkeypatch.setenv("DREX_API_KEY", "nace_sk_test")

    with pytest.raises(drex.DrexError) as exc:
        drex.check()
    assert exc.value.code == "bad_response"


# --- the endpoint -----------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app

    monkeypatch.delenv("DREX_API_KEY", raising=False)
    monkeypatch.setattr(drex, "ENV_PATH", __import__("pathlib").Path("Z:/definitely/missing.env"))
    with TestClient(create_app()) as test_client:
        yield test_client


def test_check_endpoint_reports_a_missing_key_without_crashing(client):
    body = client.post("/api/drex/check").json()

    assert body["ok"] is False
    assert body["code"] == "no_key"
    assert body["has_key"] is False


def test_check_endpoint_answers_with_a_canned_result(client, monkeypatch):
    monkeypatch.setattr(drex, "check", lambda **kw: {
        "ok": True, "noul": 0.935, "ms": 970, "model": "drex-v1.5", "has_key": True})
    monkeypatch.setattr(drex, "has_key", lambda: True)

    body = client.post("/api/drex/check").json()

    assert body["ok"] is True
    assert body["noul"] == 0.935
