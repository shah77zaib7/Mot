"""First start after Phase 5B-1: copy the old folder into the new home.

Rules (they are the whole point of this file):

1. **Back up first** — a full copy of the old folder is taken before anything
   else happens.
2. **Never delete or move the old data** — the original is only ever read.
   It stays exactly where it was, as a second copy the user can see.
3. **Copy**, file by file, into `%APPDATA%\\Mot`; an item that already exists
   in the destination is skipped, never overwritten.
4. **Report** — `migration.json` in the new folder plus one log line says what
   moved, what was skipped and where the backup is.

API keys are not touched: they live in Windows Credential Manager.
`MOT_DATA_DIR` (tests, and anyone pointing Mot at a folder by hand) skips
migration entirely — a temp folder must never pull in the real data.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import errors, paths

log = logging.getLogger("mot")

MARKER = "migration.json"
# Copy everything the old folder holds (chats, contacts, aliases, providers,
# routines, feeds, snapshot, settings, phrases) rather than a list that could
# silently miss a file Mot starts writing later.
SKIP_NAMES = {".ds_store", "desktop.ini"}


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _items(source: Path) -> list[Path]:
    return sorted(
        (p for p in source.iterdir() if p.name.lower() not in SKIP_NAMES),
        key=lambda p: (p.is_file(), p.name.lower()),
    )


def run(source: Path | None = None, dest: Path | None = None,
        backup: Path | None = None) -> dict[str, Any]:
    """Copy `source` into `dest`. Pure: the caller decides the folders."""
    source = Path(source or paths.legacy_data_dir())
    dest = Path(dest or paths.data_dir())
    report: dict[str, Any] = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "destination": str(dest),
        "backup": None,
        "copied": [],
        "skipped": [],
        "failed": [],
        "bytes": 0,
    }
    if not source.is_dir():
        report["note"] = "no old data folder to migrate"
        return report

    # 1. back up, before a single file is copied anywhere else
    backup = Path(backup) if backup else source.with_name(
        f"{source.name}-backup-{_stamp()}")
    if not backup.exists():
        try:
            shutil.copytree(source, backup)
        except OSError as exc:
            raise RuntimeError(
                f"Mot could not back up your old data first: "
                f"{errors.friendly(exc)}\n\nYour old data was not changed - "
                f"it is still in {source}."
            ) from exc
    report["backup"] = str(backup)

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Mot could not write into {dest}: {errors.friendly(exc)}\n\n"
            f"Your old data was not changed - it is still in {source}."
        ) from exc

    # 2. copy (never move, never delete, never overwrite what is already there)
    for item in _items(source):
        target = dest / item.name
        try:
            if target.exists():
                report["skipped"].append(item.name)
                continue
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
            report["copied"].append(item.name)
            report["bytes"] += item.stat().st_size if item.is_file() else _size(target)
        except OSError as exc:  # keep going: the rest of the data still lands
            report["failed"].append({"item": item.name, "why": str(exc)})
            log.warning("migration: could not copy %s (%s)", item.name, exc)
    return report


def _size(path: Path) -> int:
    try:
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    except OSError:
        return 0


def already_done() -> bool:
    """One-shot: the marker is written the first time `ensure()` runs."""
    return (paths.data_dir() / MARKER).is_file()


def ensure() -> dict[str, Any]:
    """Called once at startup, before any module reads a data path."""
    if os.environ.get(paths.DATA_ENV, "").strip():
        return {"skipped": True, "note": f"{paths.DATA_ENV} is set"}
    dest = paths.data_dir()
    if already_done():
        return {"skipped": True, "note": "already migrated"}
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("migration: cannot create %s (%s)", dest, exc)
        return {"skipped": True, "note": str(exc)}

    source = paths.legacy_data_dir()
    if not source.is_dir():
        report = {"at": datetime.now().isoformat(timespec="seconds"),
                  "source": str(source), "destination": str(dest),
                  "backup": None, "copied": [], "skipped": [],
                  "failed": [], "note": "no old data folder to migrate"}
        _write_marker(dest, report)
        return report

    log.info("migration: copying the old data folder into %s", dest)
    try:
        report = run(source, dest)
    except OSError as exc:
        log.exception("migration failed")
        raise RuntimeError(
            f"Mot could not copy your old data into {dest}.\n"
            f"{errors.friendly(exc)}\n\n"
            f"Your old data was not changed - it is still in {source}."
        ) from exc
    _write_marker(dest, report)

    log.info(
        "migration: %s — copied %d item(s) (%.1f MB) from %s to %s, "
        "%d already there, backup at %s",
        "done" if not report["failed"] else "finished with problems",
        len(report["copied"]), report["bytes"] / 1_048_576,
        report["source"], report["destination"], len(report["skipped"]),
        report["backup"],
    )
    for name in report["copied"]:
        log.info("migration: copied %s", name)
    if report["skipped"]:
        # Something was already in the new folder before the first migration —
        # it wins, and the old copy never arrived. Say so loudly: this is how a
        # person notices their data is missing instead of weeks later.
        log.warning(
            "migration: %d item(s) were already in the new folder and were left "
            "untouched, so the old copies did not come over: %s",
            len(report["skipped"]), ", ".join(report["skipped"]))
        log.warning(
            "migration: if something looks missing, the old data is still in %s "
            "and the backup is at %s",
            report["source"], report["backup"])
    return report


def _write_marker(dest: Path, report: dict[str, Any]) -> None:
    try:
        (dest / MARKER).write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        log.warning("migration: could not write %s", dest / MARKER, exc_info=True)


def report() -> dict[str, Any]:
    """What the last migration did (for the log and for us, later)."""
    marker = paths.data_dir() / MARKER
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
