"""FastAPI app, static frontend, and the pywebview desktop shell."""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    actions,
    apps as apps_api,
    chat,
    chats,
    contacts as contacts_api,
    drex,
    feeds as feeds_api,
    providers,
    routines as routines_api,
)
from .core import config

LOG_PATH = config.LOG_DIR / "mot.log"

FALLBACK_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Mot</title>
<style>body{font-family:'Segoe UI',sans-serif;background:#0c0d10;color:#e7e8ea;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{max-width:460px;text-align:center;padding:32px}
code{background:#1a1c20;padding:2px 6px;border-radius:6px}</style></head>
<body><div class="card">
<h1>Mot</h1><p>The interface hasn't been built yet.</p>
<p>Run this once:</p>
<p><code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>
</div></body></html>"""


def setup_logging(quiet: bool = False) -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3,
                                       encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    if not quiet and sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_DISCOVERY_STARTED = False


def _start_discovery() -> None:
    """Scan the Start Menu once in the background -> data/apps.json."""
    global _DISCOVERY_STARTED
    if _DISCOVERY_STARTED:
        return
    _DISCOVERY_STARTED = True
    from .core import apps

    threading.Thread(target=apps.rescan_if_stale, daemon=True).start()


def create_app() -> FastAPI:
    app = FastAPI(title="Mot", docs_url=None, redoc_url=None)
    app.include_router(chat.router)
    app.include_router(chats.router)
    app.include_router(providers.router)
    app.include_router(actions.router)
    app.include_router(apps_api.router)
    app.include_router(routines_api.router)
    app.include_router(contacts_api.router)
    app.include_router(feeds_api.router)
    app.include_router(drex.router)

    _start_discovery()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    index = config.FRONTEND_DIST / "index.html"
    if index.exists():
        app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True),
                  name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        @app.get("/{path:path}", response_class=HTMLResponse)
        def fallback(request: Request, path: str = "") -> HTMLResponse:  # noqa: ARG001
            if path.startswith("api/"):
                return HTMLResponse('{"detail":"Not found"}', status_code=404)
            return HTMLResponse(FALLBACK_PAGE)

    @app.middleware("http")
    async def no_cache_for_index(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:  # runs in a thread, not main
        pass


def start_server(port: int) -> _Server:
    server = _Server(_uvicorn_config(port))
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _uvicorn_config(port: int) -> uvicorn.Config:
    return uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,  # we log to logs/mot.log ourselves; uvicorn's default
        # formatter needs sys.stdout, which does not exist under pythonw.
    )


def wait_ready(port: int, timeout: float = 15.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    return False


def open_window(url: str, debug: bool = False) -> None:
    import webview

    webview.create_window(
        "Mot",
        url,
        width=1200,
        height=820,
        min_size=(880, 560),
        background_color="#0c0d10",
        text_select=True,
    )
    webview.start(debug=debug)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mot desktop app")
    parser.add_argument("--port", type=int, default=0, help="port (default: free port)")
    parser.add_argument("--serve", action="store_true",
                        help="run the server only, no window (for development)")
    parser.add_argument("--debug", action="store_true", help="open devtools in the window")
    args = parser.parse_args(argv)

    setup_logging(quiet=False)
    port = args.port or find_port()
    start_server(port)
    if not wait_ready(port):
        logging.getLogger("mot").error("Server did not start on port %s", port)
        return
    url = f"http://127.0.0.1:{port}/"
    if args.serve:
        print(f"Mot running at {url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    logging.getLogger("mot").info("Opening window at %s", url)
    try:
        open_window(url, debug=args.debug)
    except Exception:  # noqa: BLE001 - never die silently, log it
        logging.getLogger("mot").exception("Could not open the window")


if __name__ == "__main__":
    sys.exit(main())
