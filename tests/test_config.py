"""config.json: profile -> provider migration, keyring use, active model."""
from __future__ import annotations

import json

import pytest

from backend.core import config


@pytest.fixture
def _install(tmp_path, monkeypatch):
    """Point config at a throwaway file and swap keyring for a dict."""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    vault: dict[str, str] = {}
    monkeypatch.setattr(config, "set_secret", lambda ref, value: vault.__setitem__(ref, value))
    monkeypatch.setattr(config, "get_secret", lambda ref: vault.get(ref))
    monkeypatch.setattr(config, "delete_secret", lambda ref: vault.pop(ref, None))
    return vault


@pytest.fixture
def cfg(_install):
    """A config file that starts with no providers at all."""
    config.CONFIG_PATH.write_text(
        json.dumps({"theme": "system", "active": None, "providers": []}),
        encoding="utf-8",
    )
    return _install


@pytest.fixture
def bare_cfg(_install):
    """No config file yet — first run creates it from the defaults."""
    return _install


LEGACY = {
    "active": "Local Ollama",
    "theme": "dark",
    "profiles": [
        {"name": "Local Ollama", "model": "ollama/qwen2.5:7b",
         "api_base": "http://localhost:11434", "key_ref": None},
        {"name": "Cloud example", "model": "provider/model-name",
         "api_base": None, "key_ref": "mot-cloud-example"},
    ],
}


def test_migrates_phase1_profiles(cfg):
    config.CONFIG_PATH.write_text(json.dumps(LEGACY), encoding="utf-8")

    loaded = config.load()

    assert "profiles" not in loaded
    assert [p["name"] for p in loaded["providers"]] == ["Local Ollama"]
    provider = loaded["providers"][0]
    assert provider["base_url"] == "http://localhost:11434"
    assert provider["models"] == [{"id": "qwen2.5:7b", "tag": "local",
                                   "tag_locked": False}]
    assert loaded["active"] == {"provider_id": provider["id"],
                                "model_id": "qwen2.5:7b"}
    assert loaded["theme"] == "dark"
    # migration is written back to disk, not just held in memory
    on_disk = json.loads(config.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "profiles" not in on_disk and on_disk["providers"]


def test_migration_drops_the_placeholder_and_its_key(cfg):
    cfg["mot-cloud-example"] = "sk-leftover"
    config.CONFIG_PATH.write_text(json.dumps(LEGACY), encoding="utf-8")

    config.load()

    assert "mot-cloud-example" not in cfg
    assert all(p["name"] != "Cloud example"
               for p in config.load()["providers"])


def test_fresh_config_has_the_local_ollama_provider(bare_cfg):
    loaded = config.load()

    assert [p["name"] for p in loaded["providers"]] == ["Local Ollama"]
    assert loaded["active"]["model_id"] == "qwen2.5:7b"


def test_api_key_never_leaves_keyring(cfg):
    provider = config.save_provider(
        {"name": "Groq", "base_url": "https://api.groq.com/openai/v1",
         "models": [{"id": "llama-3.1-8b-instant", "tag": "unknown"}]},
        api_key="gsk_super_secret",
    )

    # unique account name: `mot-<provider>-<random>`, never one in reuse
    (stored_ref,) = cfg
    assert stored_ref.startswith(f"mot-{provider['id']}-")
    assert len(stored_ref) > len(f"mot-{provider['id']}-")
    dumped = json.dumps(provider)
    assert "gsk_super_secret" not in dumped
    assert "key_ref" not in provider
    assert provider["has_key"] is True
    assert provider["key_masked"] == config.KEY_MASK
    # and the config file itself never sees it
    assert "gsk_super_secret" not in config.CONFIG_PATH.read_text(encoding="utf-8")


def test_two_providers_never_share_a_keyring_name(cfg):
    first = config.save_provider({"name": "Alpha", "base_url": "https://a/v1",
                                  "models": []}, api_key="sk-a")
    second = config.save_provider({"name": "Beta", "base_url": "https://b/v1",
                                   "models": []}, api_key="sk-b")

    stored = config.load()
    refs = [p["key_ref"] for p in stored["providers"]]
    assert len(set(refs)) == 2
    assert set(cfg) == set(refs)  # exactly the two keys this test created


def test_saving_without_a_key_keeps_the_stored_one(cfg):
    provider = config.save_provider({"name": "Groq", "base_url": "https://x/v1",
                                     "models": []}, api_key="gsk_1")
    again = config.save_provider({"id": provider["id"], "name": "Groq",
                                  "base_url": "https://x/v1", "models": []},
                                 api_key=None)

    assert again["has_key"] is True
    assert list(cfg.values()) == ["gsk_1"]


def test_delete_provider_removes_the_key_and_repoints_active(cfg):
    keep = config.save_provider(
        {"name": "Ollama", "base_url": "http://localhost:11434",
         "models": [{"id": "qwen2.5:7b", "tag": "local"}]})
    gone = config.save_provider(
        {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
         "models": [{"id": "meta-llama/llama-3.3-70b:free", "tag": "free"}]},
        api_key="sk-or")
    config.set_active(gone["id"], "meta-llama/llama-3.3-70b:free")

    assert config.delete_provider(gone["id"]) is True

    assert cfg == {}  # the key went with it
    active = config.active_model()
    assert active["provider_id"] == keep["id"]
    assert active["model_id"] == "qwen2.5:7b"


def test_set_active_rejects_unknown_models(cfg):
    provider = config.save_provider(
        {"name": "Ollama", "base_url": "http://localhost:11434",
         "models": [{"id": "qwen2.5:7b", "tag": "local"}]})

    assert config.set_active(provider["id"], "qwen2.5:7b") is True
    assert config.set_active(provider["id"], "nope") is False
    assert config.set_active("p-missing", "qwen2.5:7b") is False


def test_chat_target_uses_the_right_litellm_prefix(cfg):
    ollama = config.save_provider(
        {"name": "Ollama", "base_url": "http://localhost:11434",
         "models": [{"id": "qwen2.5:7b", "tag": "local"}]})
    cloud = config.save_provider(
        {"name": "Groq", "base_url": "https://api.groq.com/openai/v1",
         "models": [{"id": "llama-3.1-8b-instant", "tag": "unknown"}]},
        api_key="gsk_1")

    local = config.chat_target(ollama["id"], "qwen2.5:7b")
    remote = config.chat_target(cloud["id"], "llama-3.1-8b-instant")

    assert local["model"] == "ollama/qwen2.5:7b"
    assert local["api_base"] == "http://localhost:11434"
    assert local["label"] == "qwen2.5:7b"
    assert remote["model"] == "openai/llama-3.1-8b-instant"
    assert remote["api_base"] == "https://api.groq.com/openai/v1"
    assert remote["label"] == "llama-3.1-8b-instant"
    assert remote["key_ref"].startswith(f"mot-{cloud['id']}-")


def test_chat_target_without_a_selection_falls_back_to_active(cfg):
    provider = config.save_provider(
        {"name": "Ollama", "base_url": "http://localhost:11434",
         "models": [{"id": "qwen2.5:7b", "tag": "local"}]})

    target = config.chat_target(None, None)

    assert target is not None and target["label"] == "qwen2.5:7b"
    assert config.chat_target("p-ghost", "x") is None


def test_public_provider_hides_internals(cfg):
    config.save_provider({"name": "Ollama", "base_url": "http://localhost:11434",
                          "models": [{"id": "a", "tag": "weird-tag"}]})

    public = config.list_providers()[0]

    assert set(public) == {"id", "name", "base_url", "has_key", "key_masked",
                           "models", "model_count"}
    assert public["models"][0]["tag"] == "unknown"  # normalised on save
