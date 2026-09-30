"""config.json + keyring (API keys never touch files or logs).

config.json holds providers, not profiles:

    {"theme": "system",
     "active": {"provider_id": "p-ollama", "model_id": "qwen2.5:7b"},
     "providers": [{"id", "name", "base_url", "key_ref",
                    "models": [{"id", "tag", "tag_locked"}]}]}

`tag` is free | paid | local | unknown. A key lives in Windows Credential
Manager under `key_ref` and is never returned by any API call.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

import keyring

from .fetch import is_ollama_base

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
FRONTEND_DIST = ROOT / "frontend" / "dist"
CONFIG_PATH = DATA_DIR / "config.json"

SERVICE = "Mot"
TAGS = ("free", "paid", "local", "unknown")
KEY_MASK = "••••••••"  # what the UI shows; the key itself never leaves keyring

_LOCK = threading.Lock()


# --- migration (Phase 1 profiles -> Phase 1.5 providers) --------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "provider"


def _unique_id(name: str, taken: set[str]) -> str:
    base = f"p-{_slug(name)}"
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _strip_prefix(model: str) -> str:
    return re.sub(r"^(ollama|openai)/", "", model.strip())


def _migrate(config: dict[str, Any], drop_keys: bool = False) -> dict[str, Any]:
    """Turn an old (or empty) config into the provider format, in place."""
    legacy = config.pop("profiles", None)
    if legacy is None:  # already the new shape (or a brand new file)
        config.setdefault("providers", [])
        if not isinstance(config.get("active"), dict):
            config["active"] = None
        config.setdefault("theme", "system")
        return config

    providers: list[dict[str, Any]] = []
    taken: set[str] = set()
    for profile in legacy or []:
        name = (profile.get("name") or "").strip()
        model = _strip_prefix(profile.get("model") or "")
        if not name or not model:
            continue
        if name == "Cloud example":  # Phase 1 placeholder, never a real provider
            if drop_keys and profile.get("key_ref"):
                delete_secret(profile["key_ref"])
            continue
        base_url = (profile.get("api_base") or "").strip() or None
        local = is_ollama_base(base_url) or (profile.get("model") or "").startswith("ollama/")
        providers.append(
            {
                "id": _unique_id(name, taken),
                "name": name,
                "base_url": base_url,
                "key_ref": profile.get("key_ref"),
                "models": [
                    {"id": model, "tag": "local" if local else "unknown",
                     "tag_locked": False}
                ],
            }
        )

    config["providers"] = providers
    active = None
    old_active = config.get("active")
    if isinstance(old_active, str):
        for provider in providers:
            if provider["name"] == old_active:
                active = {"provider_id": provider["id"],
                          "model_id": provider["models"][0]["id"]}
                break
    if active is None and providers:
        active = {"provider_id": providers[0]["id"],
                  "model_id": providers[0]["models"][0]["id"]}
    config["active"] = active
    config.setdefault("theme", "system")
    return config


_LEGACY_DEFAULT: dict[str, Any] = {
    "active": "Local Ollama",
    "theme": "system",
    "profiles": [
        {"name": "Local Ollama", "model": "ollama/qwen2.5:7b",
         "api_base": "http://localhost:11434", "key_ref": None},
        {"name": "Cloud example", "model": "provider/model-name",
         "api_base": None, "key_ref": "mot-cloud-example"},
    ],
}
DEFAULT_CONFIG: dict[str, Any] = _migrate(json.loads(json.dumps(_LEGACY_DEFAULT)))


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict[str, Any]:
    """Read data/config.json, creating it with defaults on first run."""
    _ensure_dirs()
    with _LOCK:
        if not CONFIG_PATH.exists():
            config = json.loads(json.dumps(DEFAULT_CONFIG))
            CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
            return config
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt config: keep a backup, fall back to defaults.
            try:
                CONFIG_PATH.replace(CONFIG_PATH.with_suffix(".json.bak"))
            except OSError:
                pass
            config = json.loads(json.dumps(DEFAULT_CONFIG))
            CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
            return config
        before = json.dumps(config, sort_keys=True)
        config = _migrate(config, drop_keys=True)
        if json.dumps(config, sort_keys=True) != before:
            CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config


def save(config: dict[str, Any]) -> None:
    _ensure_dirs()
    with _LOCK:
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


# --- providers --------------------------------------------------------------

def _find(providers: list[dict[str, Any]], provider_id: str | None) -> dict[str, Any] | None:
    if not provider_id:
        return None
    return next((p for p in providers if p.get("id") == provider_id), None)


def _clean_models(models: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in models or []:
        mid = str(item.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        tag = item.get("tag")
        out.append(
            {
                "id": mid,
                "tag": tag if tag in TAGS else "unknown",
                "tag_locked": bool(item.get("tag_locked")),
            }
        )
    return out


def public_provider(provider: dict[str, Any]) -> dict[str, Any]:
    """Shape sent to the frontend — no key_ref, no key, just a mask."""
    has_key = bool(provider.get("key_ref") and get_secret(provider["key_ref"]))
    models = [
        {"id": m["id"], "tag": m.get("tag", "unknown"),
         "tag_locked": bool(m.get("tag_locked"))}
        for m in provider.get("models", [])
    ]
    return {
        "id": provider["id"],
        "name": provider.get("name") or "Provider",
        "base_url": provider.get("base_url"),
        "has_key": has_key,
        "key_masked": KEY_MASK if has_key else None,
        "models": models,
        "model_count": len(models),
    }


def list_providers() -> list[dict[str, Any]]:
    return [public_provider(p) for p in load().get("providers", [])]


def get_provider(provider_id: str) -> dict[str, Any] | None:
    return _find(load().get("providers", []), provider_id)


def save_provider(data: dict[str, Any], api_key: str | None = None) -> dict[str, Any]:
    """Add or update a provider and its model list. Stores the key if given."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Provider name is required.")
    config = load()
    providers = config.setdefault("providers", [])
    provider = _find(providers, (data.get("id") or "").strip())
    if provider is None:
        provider = {"id": _unique_id(name, {p["id"] for p in providers}),
                    "key_ref": None}
        providers.append(provider)
    provider["name"] = name
    provider["base_url"] = (data.get("base_url") or "").strip().rstrip("/") or None
    provider["models"] = _clean_models(data.get("models"))
    if api_key:
        ref = provider.get("key_ref") or f"mot-{provider['id']}"
        set_secret(ref, api_key)
        provider["key_ref"] = ref

    active = config.get("active")
    if not isinstance(active, dict) or not active.get("provider_id"):
        first = provider["models"][0]["id"] if provider["models"] else None
        config["active"] = {"provider_id": provider["id"], "model_id": first}
    save(config)
    return public_provider(provider)


def delete_provider(provider_id: str) -> bool:
    """Remove a provider, its models and its stored key."""
    config = load()
    providers = config.get("providers", [])
    victim = _find(providers, provider_id)
    if victim is None:
        return False
    if victim.get("key_ref"):
        delete_secret(victim["key_ref"])
    config["providers"] = [p for p in providers if p.get("id") != provider_id]
    active = config.get("active")
    if isinstance(active, dict) and active.get("provider_id") == provider_id:
        remaining = config["providers"]
        config["active"] = (
            {"provider_id": remaining[0]["id"],
             "model_id": remaining[0]["models"][0]["id"] if remaining[0]["models"] else None}
            if remaining
            else None
        )
    save(config)
    return True


def set_active(provider_id: str, model_id: str) -> bool:
    config = load()
    provider = _find(config.get("providers", []), provider_id)
    if provider is None:
        return False
    if not any(m["id"] == model_id for m in provider.get("models", [])):
        return False
    config["active"] = {"provider_id": provider_id, "model_id": model_id}
    save(config)
    return True


def active_model() -> dict[str, Any] | None:
    """{provider_id, model_id, provider, model} for whatever is selected."""
    config = load()
    providers = config.get("providers", [])
    active = config.get("active") if isinstance(config.get("active"), dict) else {}
    provider = _find(providers, active.get("provider_id"))
    model = None
    if provider is not None:
        model = next((m for m in provider.get("models", [])
                      if m["id"] == active.get("model_id")), None)
    if provider is None or model is None:  # deleted behind our back: fall back
        provider = next((p for p in providers if p.get("models")), None)
        model = provider["models"][0] if provider else None
    if provider is None or model is None:
        return None
    return {"provider_id": provider["id"], "model_id": model["id"],
            "provider": provider, "model": model}


def chat_target(provider_id: str | None, model_id: str | None) -> dict[str, Any] | None:
    """Build the litellm profile for one model: ollama/<m> or openai/<m>."""
    if provider_id:
        provider = get_provider(provider_id)
        if provider is None:
            return None
        model = next((m for m in provider.get("models", []) if m["id"] == model_id), None)
        model = model or (provider["models"][0] if provider.get("models") else None)
        if model is None:
            return None
    else:
        resolved = active_model()
        if resolved is None:
            return None
        provider, model = resolved["provider"], resolved["model"]

    base_url = provider.get("base_url")
    prefix = "ollama/" if is_ollama_base(base_url) else "openai/"
    return {
        "name": provider.get("name") or "Provider",
        "model": prefix + model["id"],
        "api_base": base_url,
        "key_ref": provider.get("key_ref"),
        "label": model["id"],
    }


def active_label() -> str | None:
    resolved = active_model()
    return resolved["model"]["id"] if resolved else None


def set_theme(theme: str) -> None:
    config = load()
    config["theme"] = theme if theme in ("light", "dark", "system") else "system"
    save(config)


# --- secrets (Windows Credential Manager via keyring) ----------------------

def get_secret(ref: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, ref)
    except Exception:
        return None
    return value or None


def set_secret(ref: str, value: str) -> None:
    keyring.set_password(SERVICE, ref, value)


def delete_secret(ref: str) -> None:
    try:
        keyring.delete_password(SERVICE, ref)
    except Exception:
        pass
