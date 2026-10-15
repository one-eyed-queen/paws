from __future__ import annotations

from pathlib import Path

from ..paths import HOME, config_dirs
from ..util import fs, pkgmgr
from ..windows import IS_WINDOWS
from .model import SlsInstall

SYSTEM_LIB_DIRS = (
    Path("/usr/lib32"),
    Path("/usr/lib/i386-linux-gnu"),
    Path("/usr/lib"),
    Path("/usr/lib64"),
)


SYSTEM_APPS_DIR = Path("/usr/share/applications")

# the two builds name the same two files differently: the portable .7z ships SLSsteam.so and
# library-inject.so, the arch package installs them as libSLSsteam.so and libSLS-library-inject.so.
# checking for one name only is how a freshly installed arch build got skipped in favour of a
# system package, so both are looked for everywhere.
LIB_NAMES = ("SLSsteam.so", "libSLSsteam.so")
INJECT_NAMES = ("library-inject.so", "libSLS-library-inject.so")


def first_existing(d: Path, names) -> Path | None:
    for name in names:
        if fs.exists(d / name):
            return d / name
    return None


def lib_in(d: Path) -> Path | None:
    return first_existing(d, LIB_NAMES)


def _fill_from_dir(sls, d):
    sls.kind = "flatpak" if "flatpak" in str(d) or "var/app" in str(d) else "native"
    sls.lib_dir = d
    sls.sls_so = lib_in(d)
    sls.inject_so = first_existing(d, INJECT_NAMES)
    sls.tools = d / "tools" if fs.exists(d / "tools") else None


def _fill_from_package(sls):
    for d in SYSTEM_LIB_DIRS:
        so = d / "libSLSsteam.so"
        if not fs.exists(so):
            continue
        inject = d / "libSLS-library-inject.so"
        sls.kind = "package"
        sls.lib_dir = d
        sls.sls_so = so
        sls.inject_so = inject if fs.exists(inject) else None
        sls.managed_by = pkgmgr.system_manager() or "system package"
        return


def _desktop_injects_sls(sls):
    launchers = [
        HOME / ".local/share/applications/steam.desktop",
        HOME / ".local/share/applications/steam-native.desktop",
    ]
    if sls.managed_by:
        launchers += sorted(SYSTEM_APPS_DIR.glob("SLSsteam*.desktop"))
    for f in launchers:
        try:
            text = f.read_text()
        except OSError:
            continue
        if "LD_AUDIT" in text and "SLS" in text:
            return True
    return False


def find_sls(config: Path | None = None) -> SlsInstall | None:
    if IS_WINDOWS:
        from ..windows import port

        return port.find(config)
    sls = SlsInstall()

    candidates = [
        HOME / ".local/share/SLSsteam",
        Path("/var/lib/flatpak/app/com.valvesoftware.Steam/data/.local/share/SLSsteam"),
        HOME / ".var/app/com.valvesoftware.Steam/.local/share/SLSsteam",
        HOME / "SLSsteam",
    ]
    fallback = None
    for d in candidates:
        if not fs.exists(d):
            continue
        if lib_in(d) is None:
            fallback = fallback or d  # a folder that exists but has no library yet
            continue
        _fill_from_dir(sls, d)
        break
    else:
        if fallback is not None:
            _fill_from_dir(sls, fallback)

    if sls.sls_so is None:
        _fill_from_package(sls)

    cfg_candidates = []
    if config is not None:
        cfg_candidates.append(config)
    for d in config_dirs():
        if fs.exists(d / "config.yaml"):
            cfg_candidates.append(d / "config.yaml")
    if cfg_candidates:
        sls.config = cfg_candidates[0]
        sls.cache = sls.config.parent / "cache"
        sls.plugins = sls.config.parent / "plugins"

    if sls.sls_so is None and sls.config is None:
        return None

    sls.desktop_used = _desktop_injects_sls(sls)

    if sls.sls_so and fs.exists(sls.sls_so):
        sls.installed_ts = sls.sls_so.stat().st_mtime

    if sls.config is not None:
        sls.cache = sls.config.parent / "cache"
        sls.plugins = sls.config.parent / "plugins"
    return sls


def which_binary(name):
    from shutil import which

    return which(name)
