"""Fast-path router: which commands run without a model."""
from __future__ import annotations

import pytest

from backend.core import apps, router, routines

APPS = [
    {"name": "WhatsApp", "kind": "uwp", "target": "5319275A.WhatsAppDesktop!App", "args": ""},
    {"name": "Google Chrome", "kind": "app", "target": r"C:\Program Files\Google\chrome.exe",
     "args": ""},
]


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    apps.save({"scanned_at": 1.0, "browser": "default", "aliases": {"wa": "WhatsApp"},
               "apps": APPS})
    yield


def test_open_and_search_is_one_step_not_two_tabs():
    # bug #1 (Phase 3.5): opening the site first made a second tab
    steps = router.parse("open YouTube and search lo-fi")

    assert steps == [
        {"action": "search_in_browser", "site": "youtube", "query": "lo-fi"},
    ]


def test_a_search_on_another_site_keeps_both_steps():
    steps = router.parse("open YouTube and search gold price on google")

    assert steps == [
        {"action": "open_url", "url": "https://www.youtube.com", "site": "youtube"},
        {"action": "search_in_browser", "site": "google", "query": "gold price"},
    ]


def test_search_on_each_supported_site():
    assert router.parse("search gold price on google maps")[0] == {
        "action": "search_in_browser", "site": "maps", "query": "gold price"}
    assert router.parse("find silver on bing")[0]["site"] == "bing"
    assert router.parse("search x on somewhere")[0]["site"] == "google"  # unknown -> Google


def test_search_without_a_site_goes_to_google():
    step = router.parse("search weather")[0]
    assert step == {"action": "search_in_browser", "site": "google", "query": "weather"}


def test_go_to_url_and_bare_url():
    assert router.parse("go to https://tradingview.com/chart")[0]["url"] == \
        "https://tradingview.com/chart"
    assert router.parse("open youtube.com/watch?v=x")[0]["url"] == "youtube.com/watch?v=x"


def test_open_known_site_uses_its_url():
    step = router.parse("open netflix")[0]
    assert step["url"] == "https://www.netflix.com"


def test_open_app_and_alias():
    assert router.parse("open WhatsApp")[0] == {"action": "open_app", "name": "WhatsApp"}
    # a bare app name as a chained segment
    assert router.parse("open chrome then whatsapp") == [
        {"action": "open_app", "name": "chrome"},
        {"action": "open_app", "name": "whatsapp"},
    ]


def test_install_is_its_own_rule():
    assert router.parse("install vlc")[0] == {"action": "install_app", "name": "vlc"}
    assert router.parse("please install vlc")[0]["name"] == "vlc"


def test_routine_by_name_and_with_a_verb():
    assert router.parse("morning setup")[0] == {"action": "run_routine",
                                                "name": "Morning setup"}
    assert router.parse("run my morning setup")[0] == {"action": "run_routine",
                                                       "name": "Morning setup"}
    assert router.parse("start Morning Setup")[0]["name"] == "Morning setup"


def test_politeness_and_case_are_ignored():
    assert router.parse("Please open NETFLIX")[0]["action"] == "open_url"
    assert router.parse("open youtube now")[0]["url"] == "https://www.youtube.com"


def test_unknown_input_falls_through_to_chat():
    assert router.parse("why is gold moving today") is None
    assert router.parse("open youtube and tell me a joke") is None
    assert router.parse("hello") is None
    assert router.parse("") is None
    # a bare sentence that only fuzzy-matches an app is not an open command
    assert router.parse("whatsapp zara hi") is None


def test_search_for_does_not_leak_the_word_for():
    assert router.parse("search for flights to tokyo")[0]["query"] == "flights to tokyo"
    assert router.parse("search for gold price on bing")[0] == {
        "action": "search_in_browser", "site": "bing", "query": "gold price"}


def test_parse_parts_hands_only_the_unknown_segments_to_the_model():
    steps, rest = router.parse_parts("open youtube and tell me a joke")
    assert steps == [{"action": "open_url", "url": "https://www.youtube.com",
                      "site": "youtube"}]
    assert rest == ["tell me a joke"]

    assert router.parse_parts("why is gold moving") == ([], ["why is gold moving"])
    assert router.parse_parts("open youtube") == ([{"action": "open_url",
        "url": "https://www.youtube.com", "site": "youtube"}], [])


def test_open_with_an_unresolvable_name_goes_to_the_model():
    # carry-over from 3.5: no failure card, hand the segment to the LLM router
    assert router.parse("open the gold chart on tradingview") is None
    steps, rest = router.parse_parts("open the gold chart on tradingview")
    assert steps == [] and rest == ["open the gold chart on tradingview"]

    # a known app or site still opens instantly
    assert router.parse("open chrome") == [{"action": "open_app", "name": "chrome"}]
    assert router.parse("open youtube") == [{"action": "open_url",
        "url": "https://www.youtube.com", "site": "youtube"}]


def test_a_mixed_message_still_opens_the_part_it_recognises():
    steps, rest = router.parse_parts("open chrome and open the gold chart")

    assert steps == [{"action": "open_app", "name": "chrome"}]
    assert rest == ["open the gold chart"]


# --- Phase 3.5: play rules + one tab per site -------------------------------

def test_play_on_youtube_is_one_step():
    assert router.parse("play dilbar dilbar on youtube") == [
        {"action": "play_youtube", "query": "dilbar dilbar"}]
    assert router.parse("open youtube and play dilbar dilbar") == [
        {"action": "play_youtube", "query": "dilbar dilbar"}]  # no bare homepage first


def test_play_without_a_site_is_left_for_the_model():
    assert router.parse("play dilbar dilbar") is None


def test_play_still_prefers_a_saved_routine():
    assert router.parse("play my morning setup") == [
        {"action": "run_routine", "name": "Morning setup"}]


def test_the_open_covered_by_a_search_on_another_host_stays():
    steps = router.parse("open gmail and search invoices")

    assert steps == [
        {"action": "open_url", "url": "https://mail.google.com", "site": "gmail"},
        {"action": "search_in_browser", "site": "gmail", "query": "invoices"},
    ]


def test_maps_search_covers_opening_maps():
    steps = router.parse("open google maps and search coffee near me")

    assert steps == [{"action": "search_in_browser", "site": "google maps",
                      "query": "coffee near me"}]


def test_drop_covered_opens_ignores_steps_that_open_nothing():
    steps = [
        {"action": "open_url", "url": "https://www.youtube.com", "site": "youtube"},
        {"action": "open_app", "name": "chrome"},
        {"action": "run_routine", "name": "Morning setup"},
    ]

    assert router.drop_covered_opens(steps) == steps
