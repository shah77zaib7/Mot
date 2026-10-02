"""Phase 5B-1: one data location, migration, friendly errors, splash, WebView2.

Nothing here touches a real user folder — `tests/conftest.py` points
`MOT_DATA_DIR` at a temp directory before any backend import, and the
migration tests hand `migrate.run()` explicit paths of their own.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from backend.core import errors, migrate, paths, webview2

ROOT = Path(__file__).resolve().parents[1]


# --- one data location ------------------------------------------------------

def test_data_and_log_folders_come_from_paths(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")

    assert paths.data_dir() == tmp_path
    assert paths.log_dir() == tmp_path / "logs"
    monkeypatch.delenv(paths.DATA_ENV)
    assert paths.data_dir() == Path(r"C:\Users\test\AppData\Roaming\Mot")


def test_a_missing_appdata_falls_back_to_the_home_folder(monkeypatch):
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path(r"C:\Users\test")))

    assert paths.data_dir() == Path(r"C:\Users\test\AppData\Roaming\Mot")


def test_program_files_stay_next_to_the_install(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))

    assert paths.program_root() == ROOT
    assert paths.frontend_dist() == ROOT / "frontend" / "dist"
    assert paths.icon_path() == ROOT / "assets" / "mot.ico"
    assert paths.legacy_data_dir() == ROOT / "data"
    assert paths.program_root() != paths.data_dir()  # code and data never mix


def test_no_module_hardcodes_a_data_or_log_folder():
    """The AGENTS.md rule, enforced: everything goes through paths.py."""
    forbidden = re.compile(r'/\s*["\'](data|logs)["\']')
    offenders = []
    files = list((ROOT / "backend").rglob("*.py")) + [ROOT / "run.pyw"]
    for path in files:
        if path.name in {"paths.py", "migrate.py"}:
            continue  # this is where those two paths are defined
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


# --- migration ---------------------------------------------------------------

def seed_old_folder(source: Path) -> None:
    (source / "market_ingest").mkdir(parents=True)
    (source / "mot.db").write_bytes(b"sqlite-format-3")
    (source / "config.json").write_text('{"providers": []}', encoding="utf-8")
    (source / "contacts.json").write_text('[{"name": "Sherli"}]', encoding="utf-8")
    (source / "apps.json").write_text('{"aliases": {"wa": "WhatsApp"}}', encoding="utf-8")
    (source / "routines.json").write_text('[]', encoding="utf-8")
    (source / "feeds.json").write_text('{"gold": []}', encoding="utf-8")
    (source / "news_phrases.json").write_text('{}', encoding="utf-8")
    (source / "market_ingest" / "latest.json").write_text('{"gold": []}',
                                                          encoding="utf-8")


def test_migration_copies_everything_and_leaves_the_original_alone(tmp_path):
    source, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(source)
    before = sorted(p.name for p in source.iterdir())

    report = migrate.run(source, dest)

    assert set(report["copied"]) >= {
        "mot.db", "config.json", "contacts.json", "apps.json", "routines.json",
        "feeds.json", "news_phrases.json", "market_ingest",
    }
    assert report["failed"] == []
    # the copy is real
    assert (dest / "mot.db").read_bytes() == b"sqlite-format-3"
    assert (dest / "market_ingest" / "latest.json").is_file()
    # the old folder is exactly as it was: never moved, never deleted
    assert sorted(p.name for p in source.iterdir()) == before
    assert (source / "config.json").is_file()


def test_the_old_folder_is_backed_up_before_anything_is_copied(tmp_path):
    source, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(source)

    report = migrate.run(source, dest)

    backup = Path(report["backup"])
    assert backup.parent == source.parent  # next to the original, not inside it
    assert (backup / "mot.db").read_bytes() == b"sqlite-format-3"
    assert (backup / "market_ingest" / "latest.json").is_file()


def test_a_backup_that_fails_stops_the_whole_migration(tmp_path, monkeypatch):
    source, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(source)

    def refuse(*args, **kwargs):
        raise OSError("the disk is full")

    monkeypatch.setattr(migrate.shutil, "copytree", refuse)

    with pytest.raises(RuntimeError, match="disk is full"):
        migrate.run(source, dest)

    assert not dest.exists()  # nothing was copied without a backup


def test_existing_data_is_skipped_never_overwritten(tmp_path):
    source, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(source)
    dest.mkdir()
    (dest / "config.json").write_text('{"mine": true}', encoding="utf-8")

    report = migrate.run(source, dest)

    assert "config.json" in report["skipped"]
    assert "config.json" not in report["copied"]
    assert (dest / "config.json").read_text(encoding="utf-8") == '{"mine": true}'


def test_a_destination_that_already_has_data_is_called_out_loud(
        tmp_path, monkeypatch, caplog):
    """The regression that stranded real data: a first run that happened before
    the migration existed fills the new folder with defaults, and the real
    copies then never arrive. The report has to name them."""
    legacy, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(legacy)
    dest.mkdir()
    (dest / "config.json").write_text('{"first-run": true}', encoding="utf-8")
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.setattr(paths, "data_dir", lambda: dest)
    monkeypatch.setattr(paths, "legacy_data_dir", lambda: legacy)

    with caplog.at_level(logging.WARNING, logger="mot"):
        migrate.ensure()

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "config.json" in said           # by name
    assert "left untouched" in said        # and plainly
    assert str(legacy) in said             # and where the real copy still is
    backup = json.loads(
        (dest / migrate.MARKER).read_text(encoding="utf-8"))["backup"]
    assert backup in said                   # and where the safety copy is


def test_migration_runs_once_and_writes_a_report(tmp_path, monkeypatch):
    legacy, dest = tmp_path / "old", tmp_path / "new"
    seed_old_folder(legacy)
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.setattr(paths, "data_dir", lambda: dest)
    monkeypatch.setattr(paths, "legacy_data_dir", lambda: legacy)

    first = migrate.ensure()

    assert "mot.db" in first["copied"]
    assert (dest / migrate.MARKER).is_file()
    assert migrate.report()["copied"] == first["copied"]

    second = migrate.ensure()
    assert second["skipped"] is True
    assert (dest / "mot.db").read_bytes() == b"sqlite-format-3"


def test_a_temp_data_folder_is_never_migrated_into(tmp_path, monkeypatch):
    """MOT_DATA_DIR is the test/override switch — it must pull in nothing."""
    monkeypatch.setenv(paths.DATA_ENV, str(tmp_path))

    report = migrate.ensure()

    assert report["skipped"] is True
    assert not (tmp_path / migrate.MARKER).exists()
    assert not (tmp_path / "mot.db").exists()
    assert not (tmp_path / "config.json").exists()


def test_a_fresh_install_with_no_old_folder_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.delenv(paths.DATA_ENV, raising=False)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "new")
    monkeypatch.setattr(paths, "legacy_data_dir", lambda: tmp_path / "nowhere")

    report = migrate.ensure()

    assert "no old data folder" in report["note"]
    assert (tmp_path / "new" / migrate.MARKER).is_file()  # still one-shot


# --- friendly errors ---------------------------------------------------------

def test_friendly_keeps_the_message_we_wrote():
    assert errors.friendly(ValueError("Provider name is required.")) == \
        "Provider name is required."


def test_friendly_never_shows_code_noise():
    assert errors.friendly(KeyError("providers")) == errors.GENERIC
    assert errors.friendly(AttributeError("'NoneType' has no attribute x")) == \
        errors.GENERIC
    assert errors.friendly(TypeError("unsupported operand type(s)")) == errors.GENERIC
    assert errors.friendly(RuntimeError("")) == errors.GENERIC


def test_friendly_stays_short():
    out = errors.friendly(RuntimeError("x" * 900))

    assert len(out) <= errors.MAX_LEN + 1
    assert out.endswith("…")
    assert "\n" not in out  # one line: it is going into a UI banner


def test_friendly_prefers_a_message_attribute():
    class Boom(Exception):
        message = "Drex said no."

    assert errors.friendly(Boom("raw internal text")) == "Drex said no."


# --- the backend's global handlers ------------------------------------------

@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.core import apps, config, feeds, routines
    from backend.main import create_app

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")

    client = TestClient(create_app(), raise_server_exceptions=False)

    def add(path: str, fn, methods: tuple[str, ...] = ("GET",)) -> None:
        """create_app mounts the built frontend at "/", so a route added
        afterwards has to go in front of the mount to be reachable at all."""
        from fastapi.routing import APIRoute

        client.app.router.routes.insert(
            0, APIRoute(path, fn, methods=list(methods)))

    client.add = add
    return client


def test_an_unhandled_error_becomes_one_plain_sentence(app_client, caplog):
    def explode() -> None:
        raise ValueError("The widget basket tipped over.")

    app_client.add("/api/boom", explode)

    with caplog.at_level(logging.ERROR, logger="mot"):
        res = app_client.get("/api/boom")

    assert res.status_code == 500
    assert res.json()["detail"] == "The widget basket tipped over."
    assert any("boom" in r.message for r in caplog.records)  # traceback logged
    assert any(r.exc_info for r in caplog.records)


def test_code_noise_is_swapped_for_a_sentence(app_client):
    def explode() -> None:
        raise KeyError("providers")

    app_client.add("/api/boom2", explode)

    res = app_client.get("/api/boom2")

    assert res.status_code == 500
    assert res.json()["detail"] == errors.GENERIC


def test_a_malformed_request_gets_a_sentence_too(app_client):
    def needs_a_number(value: int) -> dict:
        return {"value": value}

    app_client.add("/api/needs", needs_a_number)

    res = app_client.get("/api/needs")

    assert res.status_code == 422
    assert res.json()["detail"] == "Mot did not understand that request."


def test_frontend_errors_are_written_to_the_log(app_client, caplog):
    with caplog.at_level(logging.ERROR, logger="mot"):
        res = app_client.post("/api/log", json={
            "message": "Cannot read properties of undefined",
            "stack": "at Chat (App.jsx:12) | at render",
            "source": "render",
        })

    assert res.json() == {"ok": True}
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "Cannot read properties of undefined" in joined
    assert "App.jsx:12" in joined


def test_the_log_file_is_about_five_megabytes_times_three(monkeypatch, tmp_path):
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers = []
    from backend import main as backend_main
    from backend.core import config

    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    try:
        backend_main.setup_logging(quiet=True)
        handler = next(h for h in root.handlers
                       if isinstance(h, RotatingFileHandler))
        assert handler.maxBytes == 5_000_000
        assert handler.backupCount == 3
        assert (tmp_path / "logs" / "mot.log").parent.is_dir()
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in saved:
            root.addHandler(handler)


def test_the_database_really_closes_and_comes_back():
    from backend.core import db

    first = db._conn()
    assert db._CONN is first

    db.close()
    assert db._CONN is None

    second = db._conn()
    assert second is not first
    db.close()


# --- the splash ---------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="a Win32 window")
def test_the_splash_opens_and_closes():
    from backend.core import splash

    assert splash.show() is True
    assert splash.is_open() is True
    splash.close()
    assert splash.is_open() is False
    splash.close()  # closing twice is a no-op, not an error


def test_a_splash_that_cannot_open_never_blocks_a_launch(monkeypatch):
    from backend.core import splash

    splash.close()

    def no_window(ready) -> None:
        ready.set()

    monkeypatch.setattr(splash, "_build", no_window)

    assert splash.show() is False
    assert splash.is_open() is False
    splash.close()  # still a no-op


# --- WebView2 -----------------------------------------------------------------

def test_no_message_when_the_runtime_is_installed(monkeypatch):
    monkeypatch.setattr(webview2, "installed", lambda: True)

    assert webview2.missing_message() is None


def test_a_missing_runtime_points_at_the_download(monkeypatch):
    monkeypatch.setattr(webview2, "installed", lambda: False)

    message = webview2.missing_message()

    assert message is not None
    assert webview2.DOWNLOAD_URL in message
    assert "untouched" in message


def test_a_probe_that_explodes_does_not_stop_mot(monkeypatch):
    def boom() -> bool:
        raise OSError("the registry is not readable")

    assert webview2.missing_message(check=boom) is None


def test_the_installed_check_agrees_with_this_machine():
    # Mot runs on this machine, so a runtime really is installed there —
    # if the probe ever disagreed, every launch would show the download box.
    assert webview2.installed() is True
    assert webview2.missing_message() is None
    assert webview2.REG_PATH.endswith(r"EdgeUpdate\Clients")
    assert webview2.CLIENT_ID.startswith("{")  # the evergreen client id
