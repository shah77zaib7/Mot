"""The preset chips must point at the provider's real API root.

Verified against each provider's documentation (and litellm's own defaults,
which is what actually sends the chat request):
  Ollama      http://localhost:11434          (docs: quickstart)
  LM Studio   http://localhost:1234/v1        (docs: local server)
  OpenRouter  https://openrouter.ai/api/v1    (docs: API reference)
  Groq        https://api.groq.com/openai/v1  (litellm GROQ_API_BASE)
  DeepSeek    https://api.deepseek.com/v1     (both /v1/models and /models answer)
  NVIDIA      https://integrate.api.nvidia.com/v1 (litellm NVIDIA_NIM_API_BASE)
  OpenAI      https://api.openai.com/v1
"""
from __future__ import annotations

from backend.core.fetch import PRESETS, is_lmstudio_base, is_ollama_base

EXPECTED = {
    "Ollama": "http://localhost:11434",
    "LM Studio": "http://localhost:1234/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "NVIDIA": "https://integrate.api.nvidia.com/v1",
    "OpenAI": "https://api.openai.com/v1",
    "Custom": "",
}


def test_preset_order_matches_the_settings_chips():
    assert [p["label"] for p in PRESETS] == [
        "Ollama", "LM Studio", "OpenRouter", "Groq", "DeepSeek", "NVIDIA", "OpenAI",
        "Custom",
    ]


def test_preset_urls_are_correct():
    for preset in PRESETS:
        assert preset["base_url"] == EXPECTED[preset["label"]], preset["label"]


def test_every_preset_except_custom_names_itself():
    for preset in PRESETS:
        if preset["label"] == "Custom":
            assert preset["name"] == ""
        else:
            assert preset["name"] == preset["label"]


def test_local_server_detection():
    assert is_ollama_base("http://localhost:11434")
    assert is_ollama_base("http://127.0.0.1:11434/")
    assert not is_ollama_base("https://api.openai.com/v1")
    assert is_lmstudio_base("http://localhost:1234/v1")
    assert not is_lmstudio_base("http://localhost:11434")
