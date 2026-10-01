"""Shared test setup: repo on sys.path + a throwaway HTTP server per test."""
from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
