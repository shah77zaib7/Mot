"""Shared test setup: repo on sys.path, a throwaway data folder, an HTTP server.

The whole suite runs against a temp data folder (`MOT_DATA_DIR`), set **before**
any backend module is imported so `config.py` / `db.py` compute their paths
from it. No test can read or write `%APPDATA%\\Mot` or the repo's `data/`, and
`migrate.ensure()` leaves the real data alone while it is set.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_DATA_ROOT = Path(tempfile.mkdtemp(prefix="mot-tests-"))
os.environ["MOT_DATA_DIR"] = str(_DATA_ROOT)

atexit.register(shutil.rmtree, _DATA_ROOT, ignore_errors=True)

# Enough of a Start Menu for the matcher tests: a fresh data folder has no
# discovery cache, and running the real PowerShell scan from a test would be
# slow, noisy and machine-dependent.
SEED_APPS = [
    {"name": "Google Chrome", "kind": "app",
     "target": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
     "args": ""},
    {"name": "Microsoft Edge", "kind": "app",
     "target": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
     "args": ""},
    {"name": "Notepad", "kind": "app", "target": r"C:\Windows\System32\notepad.exe",
     "args": ""},
    {"name": "WhatsApp", "kind": "app",
     "target": r"C:\Users\test\AppData\Local\WhatsApp\WhatsApp.exe", "args": ""},
    {"name": "VLC media player", "kind": "app", "target": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
     "args": ""},
    {"name": "Calculator", "kind": "uwp", "target": "Microsoft.WindowsCalculator!App",
     "args": ""},
]


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """No test may read or write real user data, live headlines or the web.

    The saved snapshot, the phrase list and the refresh settings all live
    under data/market_ingest and data/ — point them at tmp_path so tests never
    touch live headlines (and never reach the network for them). The app list
    is seeded so the matcher never needs a real Start Menu scan, and the
    database connection is dropped between tests so each one gets its own.
    """
    from backend.core import apps, db, feeds, ingest, phrases, snapshot
    from backend.tools import news

    monkeypatch.setattr(snapshot, "DIR", tmp_path / "market_ingest")
    monkeypatch.setattr(snapshot, "PATH", tmp_path / "market_ingest" / "latest.json")
    monkeypatch.setattr(phrases, "PATH", tmp_path / "news_phrases.json")
    # never reach the real web from a test; news_fallback has its own test
    monkeypatch.setattr(news, "_web_fallback", lambda topic: [])

    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    apps.save({"scanned_at": time.time(), "browser": "default",
               "aliases": {}, "apps": SEED_APPS})

    db.close()  # a connection opened by an earlier test points at its folder
    phrases.reset()
    feeds.clear_cache()
    yield
    phrases.reset()
    feeds.clear_cache()
    ingest.stop()
    db.close()


@pytest.fixture
def serve():
    """serve(routes, delay=0) -> base URL. routes: path -> (status, body)."""
    servers: list[ThreadingHTTPServer] = []

    def start(routes: dict, delay: float = 0.0, seen: list | None = None) -> str:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # noqa: ARG002 - keep test output quiet
                pass

            def _reply(self, body_sent: bytes) -> None:
                if seen is not None:
                    seen.append((self.path, self.headers.get("Authorization")))
                if delay:
                    time.sleep(delay)
                status, body = routes.get(self.path, (404, '{"detail":"Not Found"}'))
                if callable(body):
                    body = body(body_sent)
                if isinstance(body, str):
                    body = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server naming
                self._reply(b"")

            def do_POST(self) -> None:  # noqa: N802 - http.server naming
                length = int(self.headers.get("Content-Length") or 0)
                self._reply(self.rfile.read(length) if length else b"")

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield start

    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()
