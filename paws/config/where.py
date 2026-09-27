from __future__ import annotations

from pathlib import Path

from ..paths import config_dirs


def find_config() -> Path | None:
    for d in config_dirs():
        p = d / "config.yaml"
        if p.exists():
            return p
    return None
