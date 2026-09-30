"""Tools: search URLs, open_url, app discovery/matching, winget parsing.

Nothing here launches a real app — launchers and PowerShell are faked.
"""
from __future__ import annotations

import json

import pytest

from backend.core import apps
from backend.tools import install, launch, open_url as open_url_tool, registry, search

FAKE_APPS = [
    {"name": "WhatsApp", "kind": "uwp", "target": "5319275A.WhatsAppDesktop!App", "args": ""},
    {"name": "Google Chrome", "kind": "app",
     "target": r"C:\Program Files\Google\Chrome\Application\chrome.exe", "args": "--start-maximized"},
    {"name": "Notepad", "kind": "app", "target": r"C:\Windows\System32\notepad.exe", "args": ""},
]


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {"wa": "WhatsApp"},
               "apps": FAKE_APPS})
    yield


# --- search ----------------------------------------------------------------

def test_search_urls_for_every_engine():
    assert search.search_url("youtube", "lo-fi") == \
        "https://www.youtube.com/results?search_query=lo-fi"
    assert search.search_url("google", "gold price") == \
        "https://www.google.com/search?q=gold+price"
    assert search.search_url("bing", "silver") == "https://www.bing.com/search?q=silver"
    assert search.search_url("duckduckgo", "news") == "https://duckduckgo.com/?q=news"
    assert search.search_url("google maps", "paris") == \
        "https://www.google.com/maps/search/paris"


def test_unknown_search_site_falls_back_to_google():
    assert search.engine_key("frobnicate") == "google"
    assert search.search_url("frobnicate", "x").startswith("https://www.google.com/")


def test_search_tool_opens_the_url(monkeypatch):
    opened = {}
    monkeypatch.setattr(launch, "open_url",
                        lambda url, browser="default": opened.update(url=url) or {"ok": True})

    result = registry.call("search_in_browser", {"site": "youtube", "query": "lo-fi"})

    assert result["ok"] is True
    assert opened["url"] == "https://www.youtube.com/results?search_query=lo-fi"
    assert "YouTube" in result["message"]


# --- open_url --------------------------------------------------------------

def test_open_url_adds_https_and_labels_the_host():
    assert open_url_tool.normalize_url("example.com") == "https://example.com"
    assert open_url_tool.normalize_url("https://x.com") == "https://x.com"
    assert open_url_tool.label_for("https://www.youtube.com/watch") == "youtube.com"


def test_open_url_uses_the_preferred_browser(monkeypatch):
    seen = {}
    monkeypatch.setattr(apps, "browser", lambda: "brave")
    monkeypatch.setattr(launch, "open_url",
                        lambda url, browser="default": seen.update(browser=browser) or {"ok": True})

    result = registry.call("open_url", {"url": "https://a.b"})

    assert result["ok"] is True and seen["browser"] == "brave"


def test_open_url_missing_browser_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(launch, "browser_exe", lambda kind: None)
    monkeypatch.setattr(launch.os, "startfile", lambda url: None)

    result = launch.open_url("https://a.b", browser="brave")

    assert result == {"ok": True, "browser": "default", "fallback": "brave"}


# --- app discovery + matching ---------------------------------------------

def test_scan_cleans_duplicates_and_empty_targets(monkeypatch):
    monkeypatch.setattr(apps, "_run_ps", lambda script: json.dumps([
        {"name": "Chrome", "kind": "app", "target": r"C:\chrome.exe", "args": ""},
        {"name": "Chrome", "kind": "app", "target": "", "args": ""},   # dropped
        {"name": "Calculator", "kind": "uwp", "target": "Microsoft.WindowsCalculator!App",
         "args": ""},
    ]))

    found = apps.scan()

    assert found == 2
    assert [a["name"] for a in apps.list_apps()] == ["Chrome", "Calculator"]


def test_matching_exact_alias_contains_and_fuzzy():
    assert apps.match("notepad")["name"] == "Notepad"
    assert apps.match("wa")["name"] == "WhatsApp"          # alias
    assert apps.match("chrome")["name"] == "Google Chrome"  # contained in the name
    assert apps.match("whats app")["name"] == "WhatsApp"    # fuzzy
    assert apps.match("definitely not an app") is None


def test_claims_only_when_the_name_really_is_that_app():
    assert apps.claims("notepad") is True
    assert apps.claims("whats app") is True   # exact once punctuation is dropped
    assert apps.claims("wa") is True          # alias
    assert apps.claims("whatsapp zara hi") is False  # fuzzy-only: not this app
    assert apps.claims("definitely not an app") is False


def test_alias_editing_persists():
    apps.set_aliases({"sia": "Notepad"})

    assert apps.load()["aliases"] == {"sia": "Notepad"}
    assert apps.match("sia")["name"] == "Notepad"


def test_launch_app_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(launch, "_spawn", lambda args: calls.append(args))

    assert launch.launch_app(FAKE_APPS[1])["ok"] is True   # exe + args
    assert launch.launch_app(FAKE_APPS[0])["ok"] is True   # uwp via shell:AppsFolder

    assert calls[0][0].endswith("chrome.exe") and calls[0][1] == "--start-maximized"
    assert calls[1] == ["explorer.exe", "shell:AppsFolder\\5319275A.WhatsAppDesktop!App"]


def test_launch_app_without_a_target_fails():
    assert launch.launch_app({"kind": "app", "target": ""})["ok"] is False


def test_open_app_tool_reports_a_friendly_miss():
    result = registry.call("open_app", {"name": "nope nope"})

    assert result["ok"] is False
    assert "Couldn\u2019t find an app" in result["message"]
    assert "install nope nope" in result["data"]["hint"]


# --- winget ----------------------------------------------------------------

SEARCH_OUTPUT = """\
Name                           Id                            Version        Match        Source
-----------------------------------------------------------------------------------------------
VideoLAN VLC                   VideoLAN.VLC                 3.0.20                      winget
VLC media player (winget)      VideoLAN.VLC.old             2.0                                   winget
Not a package                                                        1.0
"""


def test_parse_winget_search_output():
    rows = install.parse_search(SEARCH_OUTPUT)

    assert rows[0] == {"name": "VideoLAN VLC", "id": "VideoLAN.VLC", "version": "3.0.20"}
    assert all("Not a package" not in row["name"] for row in rows)


def test_resolve_picks_the_closest_package(monkeypatch):
    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(install, "run_winget",
                        lambda args, timeout=0, on_line=None: (0, SEARCH_OUTPUT))

    assert install.resolve("vlc")["id"] == "VideoLAN.VLC"
    assert install.resolve("something-else") is None  # below the score threshold


def test_install_runs_winget_with_the_package_id(monkeypatch):
    seen = {}

    def fake_run(args, timeout=0, on_line=None):
        seen["args"] = args
        if on_line:
            on_line("Installing package…")
        return 0, "Successfully installed"

    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(install, "run_winget", fake_run)

    result = install.install({"id": "VideoLAN.VLC", "name": "VLC"})

    assert result["ok"] is True
    assert seen["args"][:3] == ["install", "--id", "VideoLAN.VLC"]
    assert "--silent" in seen["args"]


def test_install_failure_is_friendly(monkeypatch):
    monkeypatch.setattr(install, "WINGET", "winget.exe")
    monkeypatch.setattr(install, "run_winget",
                        lambda args, timeout=0, on_line=None: (1, "error: access denied"))

    result = install.install({"id": "X.Y", "name": "Thing"})

    assert result["ok"] is False and "access denied" in result["message"]
