from __future__ import annotations

import os
from pathlib import Path

from ..paths import DATA_DIR, paws_home

HOME = Path.home()


BUNDLED_DIR = Path(os.environ.get("PAWS_BUNDLED_ART") or DATA_DIR / "ascii")


PALETTES_FILE = DATA_DIR / "ascii" / "palettes.json"


def user_cfg_dir() -> Path:
    return Path(os.environ.get("PAWS_CONFIG_DIR") or paws_home())


def user_art_dir() -> Path:
    return Path(os.environ.get("PAWS_ART_DIR", user_cfg_dir() / "ascii"))
