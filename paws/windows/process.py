from __future__ import annotations

import csv
import io
import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashing up for tasklist/taskkill


def _run(argv, timeout=10):
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW, errors="replace"
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _rows(out: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(out)) if len(row) >= 2]


def pids(image: str) -> list[str]:
    """pids of every process with that exe name, e.g. steam.exe"""
    r = _run(["tasklist", "/fo", "csv", "/nh", "/fi", f"imagename eq {image}"])
    if r is None or r.returncode != 0:
        return []
    return [row[1] for row in _rows(r.stdout) if row[0].lower() == image.lower() and row[1].isdigit()]


def kill(image: str, force: bool = False) -> bool:
    r = _run(["taskkill", *(["/f"] if force else []), "/t", "/im", image])
    return r is not None and r.returncode == 0
