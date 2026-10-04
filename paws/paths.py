from __future__ import annotations

import os
from pathlib import Path

from .windows import IS_WINDOWS

HOME = Path.home()

DATA_DIR = Path(__file__).resolve().parent / "data"


FLATPAK_ID = "com.valvesoftware.Steam"


def paws_home() -> Path:
    """paws' own folder (settings, backups, undo journal, art). ~/.config/paws, or %AppData%/paws on windows"""
    if IS_WINDOWS:
        from .windows.folders import appdata

        return appdata() / "paws"
    return Path.home() / ".config/paws"


def default_config_dir() -> Path:
    if IS_WINDOWS:
        from .windows.folders import appdata

        return appdata() / "SLSsteam"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else HOME / ".config") / "SLSsteam"


def config_dirs() -> list[Path]:
    if IS_WINDOWS:
        return [default_config_dir()]
    app = HOME / ".var/app" / FLATPAK_ID
    dirs = [
        default_config_dir(),
        HOME / ".config/SLSsteam",
        app / "config/SLSsteam",
        app / ".config/SLSsteam",
        Path("/var/lib/flatpak/app") / FLATPAK_ID / "data/.config/SLSsteam",
    ]
    seen = set()
    return [d for d in dirs if not (d in seen or seen.add(d))]
