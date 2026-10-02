"""Every path Mot uses, in one place.

Two kinds of path, and nothing else may build one by hand:

* **Program files** — the code, `assets/`, `frontend/dist`, `run.pyw` — live
  next to this file, under `program_root()`. They are part of the install and
  never move with the user's data.
* **User data** — the database, config, feeds, snapshots and the logs — lives
  in ONE folder: `%APPDATA%\\Mot`, reached with `data_dir()` / `log_dir()`.
  `MOT_DATA_DIR` overrides that single folder; tests set it to a temp
  directory, which is how the suite stays away from real user data.

Nothing else in Mot may hardcode `... / "data"` or `... / "logs"`.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Mot"
DATA_ENV = "MOT_DATA_DIR"

# backend/core/paths.py -> backend/core -> backend -> the install folder
PROGRAM_ROOT = Path(__file__).resolve().parents[2]


def program_root() -> Path:
    """Where Mot itself is installed (code, assets, the built frontend)."""
    return PROGRAM_ROOT


def data_dir() -> Path:
    """Everything the user creates: mot.db, config.json, feeds, logs."""
    override = os.environ.get(DATA_ENV, "").strip()
    if override:
        return Path(override)
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    return base / APP_NAME


def log_dir() -> Path:
    """Rotated logs (mot.log, crash.log) — a subfolder of the data folder."""
    return data_dir() / "logs"


def frontend_dist() -> Path:
    return PROGRAM_ROOT / "frontend" / "dist"


def icon_path() -> Path:
    return PROGRAM_ROOT / "assets" / "mot.ico"


def launcher() -> Path:
    return PROGRAM_ROOT / "run.pyw"


def legacy_data_dir() -> Path:
    """Where Mot kept its data before Phase 5B-1 (only read, never moved)."""
    return PROGRAM_ROOT / "data"


def legacy_log_dir() -> Path:
    return PROGRAM_ROOT / "logs"
