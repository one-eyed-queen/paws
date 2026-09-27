from __future__ import annotations

import os
from pathlib import Path

from .dirs import user_cfg_dir


def banner_name() -> str:
    env = os.environ.get("PAWS_BANNER")
    if env:
        return env
    banner_file = user_cfg_dir() / "banner"
    if banner_file.exists():
        try:
            return banner_file.read_text().strip()
        except OSError:
            pass
    return "placeholder.txt"


def set_banner(name: str) -> Path:
    config = user_cfg_dir()
    config.mkdir(parents=True, exist_ok=True)
    banner_file = config / "banner"
    banner_file.write_text(name.strip())
    return banner_file
