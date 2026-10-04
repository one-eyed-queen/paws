from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

from ..paths import HOME
from ..util import http
from .errors import SlsError

SCRIPT_URL = "https://raw.githubusercontent.com/Deadboy666/h3adcr-b/main/headcrab.sh"
MAX_SCRIPT_BYTES = 1024 * 1024
STEAM_CFG = "BootStrapperInhibitAll=enable\nBootStrapperForceSelfUpdate=disable\n"
FLATPAK_STEAM = HOME / ".var/app/com.valvesoftware.Steam"


def fetch_script():
    """headcrab's own installer, saved in the cache. returns (path, short sha256) so you can see what you're about
    to run. paws never runs it without asking, and you watch it run"""
    folder = HOME / ".cache/paws/headcrab"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        data = http.get(SCRIPT_URL, timeout=30, limit=MAX_SCRIPT_BYTES)
    except (OSError, ValueError) as error:
        raise SlsError(f"couldn't download headcrab: {error}") from error
    if not data.startswith(b"#!"):
        raise SlsError("what came back isn't headcrab's script, not running it")
    target = folder / "headcrab.sh"
    target.write_bytes(data)
    target.chmod(0o700)
    return target, hashlib.sha256(data).hexdigest()[:12]


def run_script(script):
    """headcrab asks things and shows progress, so it gets the terminal"""
    if os.name == "nt":  # bash.exe here is WSL's: it would install into the linux VM, not this windows steam
        raise SlsError("HeadCrab is a linux installer, it can't set up steam on windows")
    if not shutil.which("bash"):
        raise SlsError("bash isn't installed")
    return subprocess.run(["bash", str(script)], cwd=script.parent, env=dict(os.environ)).returncode


def steam_dirs():
    return [d for d in (HOME / ".steam/steam", FLATPAK_STEAM / ".steam/steam") if d.is_dir()]


def footprint():
    """what headcrab put on this machine that isn't SLSsteam itself"""
    found = []
    for path in (
        HOME / ".headcrab",
        HOME / ".local/share/applications/headcrab.desktop",
        HOME / ".local/share/icons/hicolor/48x48/apps/headcrab.png",
        HOME / ".local/share/CloudRedirect",
        FLATPAK_STEAM / ".local/share/CloudRedirect",
    ):
        if path.exists():
            found.append(path)
    for steam in steam_dirs():
        cfg = steam / "steam.cfg"
        if cfg.is_file() and cfg.read_text().strip() == STEAM_CFG.strip():
            found.append(cfg)
    return found


def uninstall(progress=None):
    """remove the footprint. steam.cfg is what stops steam updating itself, only ever removed when it's exactly
    the one headcrab writes"""
    removed = []
    found = footprint()
    for number, path in enumerate(found, 1):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path))
        if progress:
            progress(number / len(found))
    return removed
