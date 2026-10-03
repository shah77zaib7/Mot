"""Phase 6: Settings > Appearance picks the accent, and the order endpoint works."""
from __future__ import annotations

import json

import pytest

from backend.api.providers import FallbackIn, ThemeIn, update_fallback, update_settings
from backend.core import config


@pytest.fixture
def conf(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    config.CONFIG_PATH.write_text(
        json.dumps({"theme": "system", "active": None, "providers": []}),
        encoding="utf-8",
    )
    yield


def test_the_default_accent_matches_index_css(conf):
    css = (config.ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")

    assert f"--accent: {config.DEFAULT_ACCENT};" in css
    assert config.accent() == config.DEFAULT_ACCENT


def test_an_accent_is_saved_and_read_back(conf):
    assert config.set_accent("#6366f1") == "#6366f1"
    assert config.accent() == "#6366f1"

    on_disk = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    assert on_disk["accent"] == "#6366f1"


@pytest.mark.parametrize("junk", ["", "teal", "#12345", "#12345g", "rgb(1,2,3)", None])
def test_anything_that_is_not_a_hex_colour_falls_back(conf, junk):
    config.set_accent("#ec4899")  # a real colour first

    assert config.set_accent(junk) == config.DEFAULT_ACCENT
    assert config.accent() == config.DEFAULT_ACCENT


def test_saving_the_accent_alone_leaves_the_theme_alone(conf):
    config.set_theme("dark")

    result = update_settings(ThemeIn(accent="#0ea5e9"))

    assert result["accent"] == "#0ea5e9"
    assert result["theme"] == "dark"


def test_saving_the_theme_alone_leaves_the_accent_alone(conf):
    config.set_accent("#f59e0b")

    result = update_settings(ThemeIn(theme="light"))

    assert result["theme"] == "light"
    assert result["accent"] == "#f59e0b"


def test_the_fallback_endpoint_saves_order_and_ticks(conf):
    config.save_provider({"name": "Alpha", "base_url": "http://127.0.0.1:9/v1",
                          "models": [{"id": "a", "tag": "free"}]})
    config.save_provider({"name": "Beta", "base_url": "http://127.0.0.1:9/v1",
                          "models": [{"id": "b", "tag": "paid"}]})
    ids = {p["name"]: p["id"] for p in config.load()["providers"]}

    body = FallbackIn(models=[
        {"provider_id": ids["Beta"], "model_id": "b", "auto": True},
        {"provider_id": ids["Alpha"], "model_id": "a", "auto": False},
    ])
    saved = update_fallback(body)["fallback"]

    assert [(e["model_id"], e["auto"]) for e in saved] == [("b", True), ("a", False)]
