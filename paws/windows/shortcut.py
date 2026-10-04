"""start menu / desktop shortcuts (.lnk). windows only makes those through COM, powershell's WScript.Shell is
the one thing every windows has, so paws hands it a tiny script"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .process import NO_WINDOW


def _quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def script(link: Path, target: str, arguments: str = "", icon: Path | None = None, workdir: Path | None = None) -> str:
    lines = [
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _quote(link) + ")",
        "$s.TargetPath = " + _quote(target),
        "$s.Arguments = " + _quote(arguments),
        "$s.Description = 'SLSsteam manager'",
    ]
    if icon is not None:
        lines.append("$s.IconLocation = " + _quote(f"{icon},0"))
    if workdir is not None:
        lines.append("$s.WorkingDirectory = " + _quote(workdir))
    lines.append("$s.Save()")
    return "; ".join(lines)


def make(link: Path, target: str, arguments: str = "", icon: Path | None = None, workdir: Path | None = None):
    link.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script(link, target, arguments, icon, workdir)],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=NO_WINDOW,
    )
    if r.returncode != 0 or not link.exists():
        raise OSError((r.stderr or r.stdout or "powershell failed").strip().splitlines()[-1])
