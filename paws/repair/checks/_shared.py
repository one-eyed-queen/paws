from __future__ import annotations

import time
from pathlib import Path


def stamp():
    return time.strftime("%Y%m%dT%H%M%S")


def move_aside(path: Path) -> Path:
    destination = path.with_name(f"{path.name}.broken-{stamp()}")
    n = 0
    while destination.exists():
        n += 1
        destination = path.with_name(f"{path.name}.broken-{stamp()}-{n}")
    path.rename(destination)
    return destination


def safe_read(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None
