"""FastAPI app, static frontend, and the pywebview desktop shell.

Every heavy import (fastapi, uvicorn, each router) lives inside the function
that needs it: `run.pyw` imports this module before it knows whether another
Mot is already running, so the module itself has to stay cheap. litellm is
imported lazily by core.llm for the same reason — it costs ~10 s.
"""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

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


LOG_MAX_BYTES = 5_000_000  # mot.log rotates at ~5 MB, keeping 3 older files
LOG_BACKUPS = 3


def setup_logging(quiet: bool = False) -> None:
    from .core import config

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(config.LOG_DIR / "mot.log",
                                       maxBytes=LOG_MAX_BYTES,
                                       backupCount=LOG_BACKUPS,
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


def create_app() -> Any:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    from .api import (
        actions,
        apps as apps_api,
        chat,
        chats,
        contacts as contacts_api,
        drex,
        feeds as feeds_api,
        general as general_api,
        log as log_api,
        providers,
        routines as routines_api,
    )
    from .core import config, errors

    app = FastAPI(title="Mot", docs_url=None, redoc_url=None)
    app.include_router(chat.router)
    app.include_router(chats.router)
    app.include_router(providers.router)
    app.include_router(actions.router)
    app.include_router(apps_api.router)
    app.include_router(routines_api.router)
    app.include_router(contacts_api.router)
    app.include_router(feeds_api.router)
    app.include_router(general_api.router)
    app.include_router(drex.router)
    app.include_router(log_api.router)

    # Nothing reaches the UI as a stack trace: the traceback goes to
    # logs/mot.log and the caller gets one plain-English sentence.
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Any:
        logging.getLogger("mot").error("Unhandled error on %s %s",
                                       request.method, request.url.path,
                                       exc_info=exc)
        return JSONResponse(status_code=500,
                            content=errors.describe(request.url.path, exc))

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> Any:
        logging.getLogger("mot").warning("Bad request on %s: %s",
                                         request.url.path, exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": "Mot did not understand that request.",
                     "path": request.url.path})

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
    async def no_cache_for_index(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(port: int) -> Any:
    import uvicorn

    class _Server(uvicorn.Server):
        def install_signal_handlers(self) -> None:  # runs in a thread, not main
            pass

    server = _Server(_uvicorn_config(port))
    threading.Thread(target=server.run, daemon=True).start()
    return server


def _uvicorn_config(port: int) -> Any:
    import uvicorn

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


def create_window(url: str, hidden: bool = False) -> Any:
    import webview

    return webview.create_window(
        "Mot",
        url,
        width=1200,
        height=820,
        min_size=(880, 560),
        background_color="#0c0d10",
        text_select=True,
        hidden=hidden,
    )


def run_gui(debug: bool = False) -> None:
    """Blocks until the window really closes."""
    import webview

    webview.start(debug=debug)


def _refresh_feeds() -> None:
    """Tray > Refresh news now: one pass, off the tray thread, with a balloon."""
    from .core import ingest, tray

    log = logging.getLogger("mot")
    try:
        result = ingest.refresh_now()
    except Exception:  # noqa: BLE001 - a dead network must not kill the tray
        log.warning("refresh from the tray failed", exc_info=True)
        return
    summary = ingest.status()
    failed = summary.get("failed") or 0
    log.info("refresh from the tray: %s", result)
    if not result.get("ok"):
        return
    tray.notify(
        f"{failed} of {summary.get('sources', 0)} sources failing."
        if failed
        else "All news sources answered."
    )


def _shutdown(server: Any) -> None:
    from .core import db, hotkey, ingest, singleinstance, splash, tray
    from .core import windowctl

    log = logging.getLogger("mot")
    log.info("Mot is closing down")
    for name, stop in (
        ("starting splash", splash.close),
        ("global shortcut", hotkey.stop),
        ("tray icon", tray.stop),
        ("feed refresh", ingest.stop),
        ("window handle", windowctl.detach),
        ("single-instance lock", singleinstance.stop),
    ):
        try:
            stop()
        except Exception:  # noqa: BLE001 - one stuck piece must not block the rest
            log.warning("could not stop the %s", name, exc_info=True)
    try:
        server.should_exit = True
    except Exception:  # noqa: BLE001
        log.warning("could not stop the server", exc_info=True)
    db.close()  # last: everything that could still write to it has stopped
    log.info("Mot has stopped")


def main(argv: list[str] | None = None, started: float | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mot desktop app")
    parser.add_argument("--port", type=int, default=0, help="port (default: free port)")
    parser.add_argument("--serve", action="store_true",
                        help="run the server only, no window (for development)")
    parser.add_argument("--debug", action="store_true", help="open devtools in the window")
    parser.add_argument("--background", action="store_true",
                        help="start hidden in the tray (this is what auto-start uses)")
    args = parser.parse_args(argv)

    boot = time.perf_counter() if started is None else started
    setup_logging(quiet=False)
    log = logging.getLogger("mot")

    # Splash first: it only needs ctypes, and it has to beat keyring, the feed
    # modules and the server — the user should see something within ~100 ms.
    from .core import splash

    if not args.serve and not args.background:
        splash.show(started=boot)

    from .core import config, hotkey, ingest, migrate, singleinstance, tray
    from .core import webview2, windowctl

    # Move the old data folder into its new home first, so nothing below ever
    # reads a path from two different places. A failure raises one
    # plain-English error for the launcher to show — the old data is read-only.
    migrate.ensure()

    # One Mot at a time: the second launch has already been waved away by
    # run.pyw, but a direct `python -m backend.main` lands here too.
    if not args.serve and not singleinstance.acquire():
        log.info("Mot is already running - asked it to come to the front")
        splash.close()
        return 0

    if not args.serve:
        problem = webview2.missing_message()
        if problem:
            log.error("WebView2 runtime is missing - Mot cannot open a window")
            raise RuntimeError(problem)

    port = args.port or find_port()
    server = start_server(port)
    if not wait_ready(port):
        log.error("Server did not start on port %s", port)
        raise RuntimeError(
            f"Mot's local server did not start on port {port}.\n"
            "Another program may already be using that port, or a Python package "
            f"is missing.\nThe reason is in {config.LOG_DIR / 'mot.log'}."
        )
    url = f"http://127.0.0.1:{port}/"
    ingest.start()  # one feed refresh now, then every interval_hours (default 2)

    if args.serve:
        print(f"Mot running at {url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
        finally:
            _shutdown(server)  # Ctrl+C still stops the threads and the DB

    window = create_window(url, hidden=args.background)
    windowctl.attach(window, hidden=args.background)
    singleinstance.start_listener(windowctl.show)
    tray.start(on_open=windowctl.show, on_refresh=_refresh_feeds,
               on_quit=windowctl.quit)
    hotkey.start(config.general()["hotkey"], windowctl.toggle)

    def on_shown() -> None:
        splash.close()  # the real window is here; the waiting window goes
        log.info("startup: window on screen after %.2f s", time.perf_counter() - boot)

    try:
        window.events.shown += on_shown
        window.events.closing += windowctl.on_closing
    except Exception:  # noqa: BLE001
        log.warning("window events could not be hooked", exc_info=True)

    log.info("Opening window at %s", url)
    try:
        run_gui(debug=args.debug)
    except Exception as exc:  # noqa: BLE001 - log it, then let the launcher show it
        log.exception("Could not open the window")
        raise RuntimeError(
            f"Mot could not open its window: {exc}\n\n"
            f"The reason is in {config.LOG_DIR / 'mot.log'}."
        ) from exc
    finally:
        _shutdown(server)
    return 0


if __name__ == "__main__":
    sys.exit(main())
