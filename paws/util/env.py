from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Env:
    distro_id: str = "unknown"
    distro_like: str = ""
    is_steamdeck: bool = False
    is_tty: bool = False
    term: str = ""
    color_support: bool = True
    width: int = 80
    height: int = 24
    shell: str = ""
    xdg_session: str = ""
    tools: dict[str, str | None] = field(default_factory=dict)
    has_root: bool = False

    def tool(self, name: str) -> str | None:
        return self.tools.get(name)


def _detect_distro():
    from . import distro

    d = distro.detect()
    return d.id, " ".join(d.like)


def _is_steamdeck():
    return (
        os.path.exists("/etc/default/steam_gamemode")
        or os.path.exists("/usr/bin/jupiter-biosupdate")
        or os.path.exists("/usr/bin/steamos-update")
        or "SteamOS" in (Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else "")
    )


def _term_size():
    size = shutil.get_terminal_size()
    return size.columns, size.lines


def _can_sudo():
    if os.geteuid() == 0:
        return True
    try:
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5, text=True)
        return r.returncode == 0
    except Exception:
        return False


def detect() -> Env:
    e = Env()
    e.distro_id, e.distro_like = _detect_distro()
    e.is_steamdeck = _is_steamdeck()
    e.is_tty = sys.stdin.isatty()
    e.term = os.environ.get("TERM", "")
    e.width, e.height = _term_size()
    e.shell = os.environ.get("SHELL", "").rsplit("/", 1)[-1]
    e.xdg_session = os.environ.get("XDG_SESSION_TYPE", "")
    e.color_support = e.is_tty and os.environ.get("NO_COLOR") is None and e.term not in ("dumb", "unknown", "")
    for tool in (
        "7z",
        "7zz",
        "7za",
        "bsdtar",
        "chafa",
        "wl-copy",
        "xclip",
        "xsel",
        "pkexec",
        "notify-send",
        "xdg-open",
        "steam",
        "strings",
        "zstd",
    ):
        e.tools[tool] = shutil.which(tool)
    e.has_root = _can_sudo()
    return e


def require_tool(e: Env, tool: str) -> bool:
    return e.tools.get(tool) is not None


ENV = detect()
