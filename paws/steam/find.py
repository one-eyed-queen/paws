from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..paths import HOME
from ..sls.find import which_binary
from ..util import fs, pkgmgr
from ..windows import IS_WINDOWS
from .model import SteamInstall

WINDOWS_ROOTS = (
    Path(os.environ.get("ProgramFiles(x86)") or "C:/Program Files (x86)") / "Steam",
    Path(os.environ.get("ProgramFiles") or "C:/Program Files") / "Steam",
)


def windows_root() -> Path | None:
    """the folder steam.exe lives in. cheap (registry + a stat), no process listing"""
    from ..windows import registry

    roots = [Path(p) for p in (os.environ.get("PAWS_STEAM_ROOT"), registry.steam_path()) if p]
    return next((r for r in [*roots, *WINDOWS_ROOTS] if fs.exists(r / "steam.exe")), None)


def _find_windows_steam() -> SteamInstall | None:
    from ..windows import registry

    root = windows_root()
    if root is None:
        return None
    config_path = root / "config" / "config.vdf"
    st = SteamInstall(
        kind="windows",
        binary=os.environ.get("STEAM_BINARY") or registry.steam_exe() or str(root / "steam.exe"),
        root=root,
        config_vdf=config_path if fs.exists(config_path) else None,
        depotcache=root / "depotcache",
    )
    st.client_version, st.channel = _client_version(st)
    st.is_running = _is_running()
    return st


def find_steam() -> SteamInstall | None:
    if IS_WINDOWS:
        return _find_windows_steam()
    binary = os.environ.get("STEAM_BINARY") or which_binary("steam")

    candidates = []

    flatpak_home = HOME / ".var/app/com.valvesoftware.Steam"
    if fs.exists(flatpak_home):
        root = flatpak_home / ".steam/steam"
        config_path = flatpak_home / ".steam/root/config/config.vdf"
        dc = flatpak_home / ".steam/root/depotcache"
        st = SteamInstall(
            kind="flatpak",
            binary="flatpak run com.valvesoftware.Steam",
            root=root,
            config_vdf=config_path,
            depotcache=dc,
        )
        candidates.append(st)

    for snap_root in (HOME / "snap/steam/common/.local/share/Steam", HOME / "snap/steam/common/.steam/steam"):
        if not fs.exists(snap_root):
            continue
        config_path = snap_root / "config/config.vdf"
        candidates.append(
            SteamInstall(
                kind="snap",
                binary="snap run steam",
                root=snap_root,
                config_vdf=config_path if fs.exists(config_path) else None,
                depotcache=snap_root / "depotcache",
            )
        )

    for root_dir in (
        HOME / ".steam/steam",
        HOME / ".local/share/Steam",
        HOME / ".steam/root",
        Path("/var/lib/flatpak/app/com.valvesoftware.Steam/data/.steam/steam"),
    ):
        if not fs.exists(root_dir):
            continue
        config_path = root_dir / "config/config.vdf"
        if not fs.exists(config_path):
            config_path = root_dir / "root/config/config.vdf" if root_dir.name == "steam" else None
        dc = root_dir / "depotcache"
        st = SteamInstall(
            kind="native",
            binary=binary,
            root=root_dir,
            config_vdf=config_path if config_path and fs.exists(config_path) else None,
            depotcache=dc if fs.exists(dc) else dc,
        )
        candidates.append(st)

    if not candidates:
        return None

    chosen = None
    for c in candidates:
        v, channel = _client_version(c)
        c.client_version = v
        c.channel = channel
        if v and chosen is None:
            chosen = c
    if chosen is None:
        chosen = candidates[0]
    if chosen.config_vdf is None:
        for cand in (
            HOME / ".steam/root/config/config.vdf",
            HOME / ".steam/steam/config/config.vdf",
            Path("/var/lib/flatpak/app/com.valvesoftware.Steam/data/.steam/root/config/config.vdf"),
        ):
            if fs.exists(cand):
                chosen.config_vdf = cand
                break
    if chosen.depotcache is None:
        for cand in (
            HOME / ".steam/root/depotcache",
            HOME / ".steam/steam/depotcache",
            Path("/var/lib/flatpak/app/com.valvesoftware.Steam/data/.steam/root/depotcache"),
        ):
            if fs.exists(cand):
                chosen.depotcache = cand
                break
    chosen.is_running = _is_running()
    if chosen.kind == "native" and chosen.binary and os.path.isabs(chosen.binary):
        owner = pkgmgr.owner_of(os.path.realpath(chosen.binary))
        chosen.package = str(owner) if owner else None
    return chosen


def _client_version(st):
    if st.root is None:
        return None, "stable"
    if st.kind in ("flatpak", "windows"):
        pkg = st.root / "package"
    else:
        pkg = st.root / "package" if fs.exists(st.root / "package") else st.root.parent / "package"
    if not fs.exists(pkg):
        return None, "stable"
    pattern = "steam_client_*win*.manifest" if st.kind == "windows" else "steam_client_*ubuntu12.manifest"
    for mf in sorted(pkg.glob(pattern)):
        if "steamdeck" in mf.name:
            channel = "steamdeck"
        elif "beta" in mf.name:
            channel = "beta"
        else:
            channel = "stable"
        try:
            for line in mf.read_text().splitlines():
                if '"version"' in line:
                    return line.split('"')[-2].strip(), channel
        except OSError:
            continue
    return None, "stable"


def _is_running():
    if IS_WINDOWS:
        from ..windows import process

        return bool(process.pids("steam.exe"))
    try:
        out = subprocess.run(["ps", "-e", "-o", "comm="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(name.strip() in {"steam", "steamwebhelper", "steam-runtime"} for name in out.splitlines())
