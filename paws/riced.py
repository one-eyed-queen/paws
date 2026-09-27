from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
PARTS = [
    PACKAGE / "data/ascii",
    PACKAGE / "data/img/paws-bg.png",
    PACKAGE / "data/img/paws-banner.png",
    PACKAGE / "data/img/paws-banner-old.png",
    PACKAGE / "tui/arcade",
]


def installed():
    """the riced look needs its pictures, the art and the mini games on disk, and pillow"""
    return importlib.util.find_spec("PIL") is not None and all(part.exists() for part in PARTS)


def checkout():
    return (PACKAGE.parent / ".git").exists()


def prune():
    """minimal doesn't use any of that, so it doesn't keep it. never touches a git checkout"""
    if checkout():
        return []
    gone = []
    for part in PARTS:
        if part.is_dir():
            shutil.rmtree(part)
        elif part.exists():
            part.unlink()
        else:
            continue
        gone.append(part)
    return gone


if __name__ == "__main__":
    if sys.argv[1:] == ["prune"]:
        removed = prune()
        print(f"minimal: left out {len(removed)} riced part(s)")
