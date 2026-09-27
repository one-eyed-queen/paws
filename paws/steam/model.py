from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SteamInstall:
    kind: str
    binary: str | None = None
    root: Path | None = None
    config_vdf: Path | None = None
    depotcache: Path | None = None
    client_version: str | None = None
    channel: str = "stable"
    is_running: bool = False
    package: str | None = None
