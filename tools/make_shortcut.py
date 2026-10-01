"""Create the Mot shortcuts: Desktop\\Mot.lnk plus a Start Menu entry.

Both point at the pythonw.exe that belongs to this project and run
"C:\\Mot\\run.pyw" with C:\\Mot as the working directory, so a double-click
never depends on the .pyw file association (which may open IDLE).
Windows file associations are never touched.

Run:  python tools\\make_shortcut.py
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "run.pyw"
ICON = ROOT / "assets" / "mot.ico"
DESCRIPTION = "Mot - personal AI agent"


def powershell(script: str, timeout: int = 60) -> str:
    """Run a PowerShell snippet with no quoting risk (UTF-16LE -EncodedCommand)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell did not run")
    return result.stdout.strip()


def pythonw() -> Path:
    """The pythonw.exe this project runs on - the sibling of the current interpreter."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    if candidate.is_file():
        return candidate
    if exe.name.lower() == "pythonw.exe":
        return exe
    found = shutil.which("pythonw")
    if found:
        return Path(found)
    raise RuntimeError(
        f"Could not find pythonw.exe next to {exe}.\n"
        "Reinstall Python with the standard layout, then run this script again."
    )


def folder(name: str, fallback: Path) -> Path:
    """A Windows special folder (Desktop / Programs), respecting redirection."""
    out = powershell(f"[Environment]::GetFolderPath('{name}')")
    path = Path(out.strip()) if out.strip() else fallback
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
    return path


def quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create(path: Path, target: Path, arguments: str) -> Path:
    """Write one .lnk via the built-in WScript.Shell COM object (no dependencies)."""
    script = "\n".join(
        [
            f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quoted(str(path))})",
            f"$s.TargetPath = {quoted(str(target))}",
            f"$s.Arguments = {quoted(arguments)}",
            f"$s.WorkingDirectory = {quoted(str(ROOT))}",
            f"$s.IconLocation = {quoted(str(ICON) + ',0')}",
            f"$s.Description = {quoted(DESCRIPTION)}",
            "$s.Save()",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    powershell(script)
    if not path.is_file():
        raise RuntimeError(f"Windows did not create {path}")
    return path


def verify(path: Path) -> str:
    """Read the shortcut back so a wrong target is caught here, not at double-click."""
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({quoted(str(path))})\n"
        "Write-Output $s.TargetPath\nWrite-Output $s.Arguments\nWrite-Output $s.WorkingDirectory"
    )
    target, arguments, workdir = powershell(script).splitlines()[:3]
    return f"{target} {arguments}  (in {workdir})"


def main() -> int:
    if not LAUNCHER.is_file():
        print(f"error: {LAUNCHER} is missing", file=sys.stderr)
        return 1
    if not ICON.is_file():
        import mot_icon  # tools/mot_icon.py sits next to this script

        mot_icon.write_ico(ICON)
        print(f"created {ICON}")

    target = pythonw()
    arguments = f'"{LAUNCHER}"'

    desktop = folder("Desktop", Path.home() / "Desktop")
    programs = folder(
        "Programs",
        Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows"
        / "Start Menu" / "Programs",
    )

    shortcuts = [
        create(desktop / "Mot.lnk", target, arguments),
        create(programs / "Mot.lnk", target, arguments),
    ]
    for shortcut in shortcuts:
        print(f"created {shortcut}")
        print(f"    -> {verify(shortcut)}")
    print("\nDouble-click the Desktop shortcut to start Mot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
