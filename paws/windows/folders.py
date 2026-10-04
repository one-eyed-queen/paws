from __future__ import annotations

import os
from pathlib import Path


def appdata() -> Path:
    """%AppData% (roaming). SLSsteam keeps its config.yaml in %AppData%/SLSsteam"""
    value = os.environ.get("APPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Roaming"


def local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else Path.home() / "AppData" / "Local"


def start_menu() -> Path:
    return appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def desktop() -> Path:
    """the real desktop folder, onedrive moves it so ask the shell first"""
    from .registry import shell_folder

    found = shell_folder("Desktop")
    return Path(found) if found else Path.home() / "Desktop"
