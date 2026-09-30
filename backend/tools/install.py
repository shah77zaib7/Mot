"""install_app — winget search + install (always behind a Confirm card).

`run_winget` is the only thing tests need to replace: nothing else here
touches the system.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from difflib import SequenceMatcher
from typing import Any, Callable

from .registry import register

WINGET_CANDIDATES = [
    shutil.which("winget") or "",
    os.path.expandvars(r"%LocalAppData%\Microsoft\WindowsApps\winget.exe"),
]
WINGET = next((p for p in WINGET_CANDIDATES if p and os.path.exists(p)), None)

INSTALL_ARGS = [
    "-e",
    "--silent",
    "--accept-package-agreements",
    "--accept-source-agreements",
    "--disable-interactivity",
]


class InstallError(Exception):
    """A winget problem worth showing to the user."""


def winget_available() -> bool:
    return WINGET is not None


def run_winget(
    args: list[str],
    timeout: float = 120.0,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """Run winget and stream its output. Replaced by tests."""
    if WINGET is None:
        raise InstallError("winget isn't available on this Windows install.")
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [WINGET, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,  # never wait on a prompt
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        clean = line.rstrip()
        lines.append(clean)
        if on_line and clean:
            on_line(clean)
    code = proc.wait(timeout=timeout)
    return code, "\n".join(lines)


def parse_search(output: str) -> list[dict[str, str]]:
    """Parse `winget search` output into [{name, id, version}].

    Columns are found by splitting on runs of spaces, so the parser does not
    depend on exact column widths.
    """
    lines = output.splitlines()
    header_at = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("Name") and "Id" in ln),
        None,
    )
    if header_at is None:
        return []
    rows: list[dict[str, str]] = []
    for line in lines[header_at + 1 :]:
        stripped = line.strip()
        if not stripped or set(stripped) <= {"-", " "}:
            continue
        fields = re.split(r"\s{2,}", stripped)
        if len(fields) < 2:
            continue
        name, pkg_id = fields[0], fields[1]
        version = fields[2] if len(fields) > 2 else ""
        # a real package id always contains a letter ("1.0" is a stray version)
        if not re.fullmatch(r"[A-Za-z0-9_.+\-]+", pkg_id) or not any(
            c.isalpha() for c in pkg_id
        ):
            continue
        rows.append({"name": name, "id": pkg_id, "version": version})
    return rows


def _score(query: str, row: dict[str, str]) -> float:
    q = query.lower().strip()
    name = row["name"].lower()
    if q == row["id"].lower() or q == name:
        return 1.0
    ratio = SequenceMatcher(None, q, name).ratio()
    if q in name or name in q:
        ratio = max(ratio, 0.8)
    if q in row["id"].lower():
        ratio = max(ratio, 0.9)
    return ratio


def resolve(name: str) -> dict[str, Any] | None:
    """Best winget package for a name, or None when nothing fits."""
    code, output = run_winget(["search", name, "--disable-interactivity"], timeout=60)
    rows = parse_search(output)
    head = next((ln for ln in output.splitlines() if ln.strip()), "")
    logging.getLogger("mot").info(
        "winget search %r -> code=%s rows=%s head=%r", name, code, len(rows), head[:120]
    )
    if not rows:
        return None
    best = max(rows, key=lambda row: _score(name, row))
    return best if _score(name, best) >= 0.55 else None


def install(package: dict[str, Any], on_line: Callable[[str], None] | None = None) -> dict[str, Any]:
    """winget install --id … — returns {ok, message}."""
    pkg_id = (package.get("id") or "").strip()
    if not pkg_id:
        return {"ok": False, "message": "No package id to install."}
    code, output = run_winget(["install", "--id", pkg_id, *INSTALL_ARGS], timeout=900, on_line=on_line)
    label = package.get("name") or pkg_id
    if code == 0:
        return {"ok": True, "message": f"Installed {label}."}
    last = next((ln for ln in reversed(output.splitlines()) if ln.strip()), "")
    detail = last[:160] if last else f"winget exited with code {code}"
    return {"ok": False, "message": f"Couldn\u2019t install {label}: {detail}"}


@register(
    "install_app",
    "Install an app with winget. The user must confirm first.",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "App to install"}},
        "required": ["name"],
    },
)
def install_app(args: dict[str, Any]) -> dict[str, Any]:
    """Search winget and ask for confirmation — no install happens here."""
    name = (args.get("name") or "").strip()
    if not name:
        return {"ok": False, "message": "No app name given.", "data": {}}
    if not winget_available():
        return {
            "ok": False,
            "message": "winget isn't available on this Windows install.",
            "data": {},
        }
    try:
        package = resolve(name)
    except InstallError as exc:
        return {"ok": False, "message": str(exc), "data": {}}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"winget took too long searching for {name}.", "data": {}}
    except OSError as exc:
        return {"ok": False, "message": f"Couldn't run winget: {exc}", "data": {}}
    if package is None:
        return {
            "ok": False,
            "message": f"winget found nothing matching \u201c{name}\u201d.",
            "data": {},
        }
    return {
        "ok": True,
        "message": f"Found {package['name']} ({package['id']}) on winget.",
        "data": {"needs_confirm": True, "package": package},
    }
