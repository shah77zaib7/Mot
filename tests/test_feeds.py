"""core/feeds.py — RSS parsing, dedupe, the 48 h window, caching, Settings API."""
from __future__ import annotations

import json
import time

import pytest

from backend.core import feeds

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>{title}</title>
<item><title>{t1}</title><link>https://example.com/a</link>
 <description>{d1}</description><pubDate>{p1}</pubDate></item>
<item><title>{t2}</title><link>https://example.com/b</link>
 <description>Second story</description><pubDate>{p2}</pubDate></item>
</channel></rss>"""


def _rss(title: str, t1: str, hours_old: float = 2.0, t2: str = "Second story") -> str:
    import email.utils
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return RSS.format(
        title=title,
        t1=t1,
        d1="Gold &amp; silver <b>rose</b> &mdash; a <b>tag</b> heavy story",
        p1=email.utils.format_datetime(now - timedelta(hours=hours_old)),
        t2=t2,
        p2=email.utils.format_datetime(now - timedelta(hours=hours_old + 1)),
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    feeds.clear_cache()
    yield feeds
    feeds.clear_cache()


def test_defaults_are_written_and_read_back(store):
    data = store.load()

    assert set(data) == {"gold", "silver", "crypto", "markets"}
    assert all(urls for urls in data.values())
    assert json.loads(store.FEEDS_PATH.read_text(encoding="utf-8")).keys() == data.keys()


def test_a_broken_file_falls_back_to_defaults(store):
    store.FEEDS_PATH.write_text("not json at all", encoding="utf-8")

    assert set(store.load()) == set(store.DEFAULTS)


def test_html_is_stripped_and_snippets_are_capped():
    assert feeds.strip_html("Gold &amp; silver <b>rose</b> &mdash; yes") == \
        "Gold & silver rose — yes"
    assert len(feeds.strip_html("x" * 500)) <= feeds.SNIPPET


def test_topic_key_accepts_aliases_and_rejects_noise(store):
    assert store.topic_key("gold") == "gold"
    assert store.topic_key("xau") == "gold"
    assert store.topic_key("Bitcoin") == "crypto"
    assert store.topic_key("stocks") == "markets"
    assert store.topic_key("blenders") is None
    assert store.topic_key("") is None


def test_fetch_feed_parses_titles_links_and_times(store, serve):
    base = serve({"/feed.xml": (200, _rss("Kitco", "Gold hits a high"))})

    title, rows = store.fetch_feed(f"{base}/feed.xml")

    assert title == "Kitco"
    assert rows[0]["title"] == "Gold hits a high"
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["source"] == "Kitco"
    assert "<b>" not in rows[0]["snippet"] and "&amp;" not in rows[0]["snippet"]
    assert 7100 < time.time() - rows[0]["ts"] < 7300  # the pubDate we sent


def test_a_dead_feed_raises_a_friendly_error(store, serve):
    base = serve({})  # everything 404s

    with pytest.raises(feeds.FeedError) as exc:
        store.fetch_feed(f"{base}/feed.xml")
    assert exc.value.code == "http"


def test_parallel_fetch_dedupes_and_sorts_newest_first(store, monkeypatch):
    seen: list[str] = []

    def fake_fetch(url: str, timeout: float = 0.0):  # noqa: ARG001
        seen.append(url)
        return "Feed", [
            {"title": f"{url} story", "url": url + "/1", "source": "s",
             "ts": int(time.time()) - 3600, "snippet": ""},
            {"title": "shared", "url": "https://dup.example/1", "source": "s",
             "ts": int(time.time()) - 7200, "snippet": ""},
        ]

    monkeypatch.setattr(store, "fetch_feed", fake_fetch)
    store.save({"gold": ["https://a.example/rss", "https://b.example/rss"]})
    items = store.topic_items("gold", limit=10)

    assert len(seen) == 2                      # both feeds at once
    assert len([i for i in items if i["title"] == "shared"]) == 1  # deduped
    assert items == sorted(items, key=lambda i: i["ts"], reverse=True)


def test_results_are_cached_and_dropped_when_feeds_change(store, monkeypatch):
    calls = []

    def fake_fetch(url: str, timeout: float = 0.0):  # noqa: ARG001
        calls.append(url)
        return "F", [{"title": "t", "url": "https://x/1", "source": "s",
                      "ts": int(time.time()), "snippet": ""}]

    monkeypatch.setattr(store, "fetch_feed", fake_fetch)
    store.save({"gold": ["https://a.example/rss"]})
    store.topic_items("gold")
    store.topic_items("gold")
    assert len(calls) == 1                     # 10 min cache

    store.save({"gold": ["https://b.example/rss"]})
    store.topic_items("gold")
    assert len(calls) == 2                     # a live edit drops the cache


def test_stories_older_than_48_hours_only_show_when_nothing_is_fresh(store, monkeypatch):
    def old_feed(url: str, timeout: float = 0.0):  # noqa: ARG001
        return "F", [{"title": "old", "url": "https://x/1", "source": "s",
                      "ts": int(time.time()) - 10 * 86400, "snippet": ""}]

    monkeypatch.setattr(store, "fetch_feed", old_feed)
    store.save({"gold": ["https://a.example/rss"]})
    items = store.topic_items("gold")

    assert items and items[0]["title"] == "old"  # a quiet weekend still shows news


def test_all_feeds_down_raises_one_friendly_error(store, monkeypatch):
    def boom(url: str, timeout: float = 0.0):  # noqa: ARG001
        raise feeds.FeedError(f"Couldn't reach {url}.", "unreachable")

    monkeypatch.setattr(store, "fetch_feed", boom)
    store.save({"gold": ["https://a.example/rss"]})

    with pytest.raises(feeds.FeedError) as exc:
        store.topic_items("gold")
    assert exc.value.code == "all_failed"


def test_search_falls_back_to_the_feed_pool(store, monkeypatch):
    rows = [
        {"title": "Gold climbs as the dollar slips", "url": "https://x/1",
         "source": "Kitco", "ts": int(time.time()), "snippet": ""},
        {"title": "Football results", "url": "https://x/2",
         "source": "BBC", "ts": int(time.time()), "snippet": ""},
    ]
    monkeypatch.setattr(store, "all_items", lambda limit=40: rows)  # noqa: ARG005

    hits = store.search("gold price")

    assert len(hits) == 1 and hits[0]["source"] == "Kitco"


def test_test_feed_reports_counts_and_rejects_junk(store, serve):
    base = serve({"/feed.xml": (200, _rss("Decrypt", "Bitcoin bounces"))})

    ok = store.test_feed(f"{base}/feed.xml")
    bad = store.test_feed("ftp://example.com/feed")

    assert ok["ok"] and ok["count"] == 2 and "Decrypt" in ok["message"]
    assert not bad["ok"] and "http" in bad["message"]
