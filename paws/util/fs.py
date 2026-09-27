from __future__ import annotations

from pathlib import Path


def exists(path) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


def is_dir(path) -> bool:
    try:
        return Path(path).is_dir()
    except OSError:
        return False


def is_file(path) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False
